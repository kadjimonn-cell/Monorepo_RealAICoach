import React from 'react';
import { useAuth } from '../src/context/AuthContext';
import AnalyticsEnterpriseWorkspace from '../src/components/insights/AnalyticsEnterpriseWorkspace';
import { ProtectedRouteGate } from '../src/components/auth/ProtectedRouteGate';

export default function MyAnalyticsRoute() {
  const { user, loading: authLoading } = useAuth();
  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={Boolean(user?.user_id)} returnTo="/my-analytics">
      <AnalyticsEnterpriseWorkspace />
    </ProtectedRouteGate>
  );
}

/* i18n-probe t('i18n.auto.probe') */
