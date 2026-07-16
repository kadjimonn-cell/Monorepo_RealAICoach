import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import api from '../services/api';
import Constants from 'expo-constants';
import { recordShellHealthEvent, recordShellHealthMetric } from '../services/shellHealthMonitor';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const CONFIG_SNAPSHOT_KEY = 'global-config-snapshot-v1';

interface AppConfig {
  version: string;
  min_supported_version: string;
  features: Record<string, boolean>;
  updates: {
    id: string;
    title: string;
    message: string;
    type: string;
    action_link?: string;
  }[];
  ui_overrides: Record<string, string>;
  limits: Record<string, any>;
}

interface ConfigContextType {
  config: AppConfig | null;
  loading: boolean;
  refreshConfig: () => Promise<void>;
  isFeatureEnabled: (featureKey: string) => boolean;
  source: 'live' | 'snapshot' | 'offline';
  recoveryActive: boolean;
}

const ConfigContext = createContext<ConfigContextType>({
  config: null,
  loading: true,
  refreshConfig: async () => {},
  isFeatureEnabled: () => false,
  source: 'live',
  recoveryActive: false,
});

function readConfigSnapshot(): AppConfig | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(CONFIG_SNAPSHOT_KEY) || window.sessionStorage.getItem(CONFIG_SNAPSHOT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeConfigSnapshot(value: AppConfig | null) {
  if (typeof window === 'undefined' || !value) return;
  try {
    const serialized = JSON.stringify(value);
    window.localStorage.setItem(CONFIG_SNAPSHOT_KEY, serialized);
    window.sessionStorage.setItem(CONFIG_SNAPSHOT_KEY, serialized);
  } catch (error) { handleAppRecoverableError({ scope: 'src/context/ConfigContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
}

export function ConfigProvider({ children }: { children: React.ReactNode }) {
  const snapshot = readConfigSnapshot();
  const [config, setConfig] = useState<AppConfig | null>(snapshot);
  const [loading, setLoading] = useState(!snapshot);
  const [source, setSource] = useState<'live' | 'snapshot' | 'offline'>(snapshot ? 'snapshot' : 'live');
  const mountedRef = useRef(true);
  const recoveryLoggedRef = useRef(false);

  const activateRecovery = useCallback((mode: 'snapshot' | 'offline', metadata: Record<string, any> = {}) => {
    setSource(mode);
    if (recoveryLoggedRef.current) return;
    recoveryLoggedRef.current = true;
    recordShellHealthMetric('fallback_activations', { source: `config_${mode}`, ...metadata });
  }, []);

  const clearRecovery = useCallback((metadata: Record<string, any> = {}) => {
    const wasRecovering = recoveryLoggedRef.current;
    recoveryLoggedRef.current = false;
    setSource('live');
    if (wasRecovering) {
      recordShellHealthMetric('route_recoveries', { source: 'config_live_refresh', ...metadata });
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const clientVersion = Constants.expoConfig?.version || '1.0.0';
      const res = await api.get(`/config/global?version=${clientVersion}`, {
        silentLoading: true,
        timeout: 12000,
      });
      if (mountedRef.current) {
        setConfig(res.data);
        writeConfigSnapshot(res.data);
        clearRecovery({ route_key: 'global_config' });
      }
    } catch (e) {
      console.error('Failed to load remote config', e);
      if (mountedRef.current) {
        const fallback = readConfigSnapshot();
        if (fallback) {
          setConfig(fallback);
          activateRecovery('snapshot', { route_key: 'global_config', reason: 'snapshot_fallback' });
          recordShellHealthEvent('cached_shell_boot_config', { route_key: 'global_config', version: fallback.version || 'snapshot' });
        } else if (!config) {
          const offlineFallback = {
            version: 'offline',
            min_supported_version: '1.0.0',
            features: { tv_reality_enabled: true, ai_phone_call_enabled: true },
            updates: [],
            ui_overrides: {},
            limits: {}
          };
          setConfig(offlineFallback);
          writeConfigSnapshot(offlineFallback);
          activateRecovery('offline', { route_key: 'global_config', reason: 'offline_fallback' });
          recordShellHealthEvent('cached_shell_boot_config', { route_key: 'global_config', version: 'offline' });
        }
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
   
  }, [activateRecovery, clearRecovery, config]);

  useEffect(() => {
    mountedRef.current = true;
    fetchConfig();
    // Fallback poll every 120s
    const interval = setInterval(fetchConfig, 120000);
    return () => { mountedRef.current = false; clearInterval(interval); };
  }, [fetchConfig]);

  const isFeatureEnabled = (key: string) => {
    if (!config) return true;
    return config.features[key] !== false;
  };

  return (
    <ConfigContext.Provider value={{ config, loading, refreshConfig: fetchConfig, isFeatureEnabled, source, recoveryActive: source !== 'live' }}>
      {children}
    </ConfigContext.Provider>
  );
}

export const useConfig = () => useContext(ConfigContext);
