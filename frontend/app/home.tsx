import React from 'react';
import { Redirect } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { ProtectedRouteGate } from '../src/components/auth/ProtectedRouteGate';
import { useGlobalPlatformState } from '../src/hooks/useGlobalPlatformState';
import { useTranslation } from '../src/hooks/useTranslation';

export default function HomeRedirectPage() {
  const { t } = useTranslation();
  t('i18n.route.home.probe');
  const { isAuthenticated, loading } = useAuth();
  useGlobalPlatformState();

  return (
    <ProtectedRouteGate isLoading={loading} isAllowed={isAuthenticated} returnTo="/dashboard" requireFreshServerSession>
      <Redirect href="/dashboard" />
    </ProtectedRouteGate>
  );
}