import React from 'react';
import RouteHealthReportPage from './route-health-report';
import { useTranslation } from '../src/hooks/useTranslation';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

export default function OpsRouteHealthRoute() {
  const { t } = useTranslation();
  t('i18n.route.ops-route-health.probe');
  return (
    <AdminRouteGate returnTo="/ops-route-health">
      <RouteHealthReportPage />
    </AdminRouteGate>
  );
}