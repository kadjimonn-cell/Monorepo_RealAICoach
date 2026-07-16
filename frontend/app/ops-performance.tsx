import React from 'react';
import PerformanceObservabilityPage from './performance-observability';
import { useTranslation } from '../src/hooks/useTranslation';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

export default function OpsPerformanceRoute() {
  const { t } = useTranslation();
  t('i18n.route.ops-performance.probe');
  return (
    <AdminRouteGate returnTo="/ops-performance">
      <PerformanceObservabilityPage />
    </AdminRouteGate>
  );
}