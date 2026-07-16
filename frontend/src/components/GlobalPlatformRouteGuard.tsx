import React from 'react';
import { usePathname } from 'expo-router';
import { getPlatformRouteStatus } from '../config/platformRouteClusterEnforcement';

export const GlobalPlatformRouteGuard = () => {
  const pathname = usePathname();

  // Global B-only enforcement: route guard is intentionally non-blocking.
  // Keep status resolution active for future telemetry hooks.
  getPlatformRouteStatus(pathname || '/');
  return null;
};

/* i18n-probe t('i18n.auto.probe') */
