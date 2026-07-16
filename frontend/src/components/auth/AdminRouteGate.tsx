import React from 'react';
import { Redirect } from 'expo-router';
import { ProtectedRouteGate } from './ProtectedRouteGate';
import { useAuth } from '../../context/AuthContext';
import { hasAdminConsoleVisibility } from '../../utils/adminAccess';

type AdminRouteGateProps = {
  children: React.ReactNode;
  returnTo: string;
};

export function AdminRouteGate({ children, returnTo }: AdminRouteGateProps) {
  const { isAuthenticated, loading, user } = useAuth();
  const isAdmin = hasAdminConsoleVisibility(user as any);

  return (
    <ProtectedRouteGate
      isLoading={loading}
      isAllowed={isAuthenticated}
      returnTo={returnTo}
      requireFreshServerSession
    >
      {isAdmin ? <>{children}</> : <Redirect href="/dashboard" />}
    </ProtectedRouteGate>
  );
}