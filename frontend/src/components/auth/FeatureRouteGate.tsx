import React from 'react';
import { Redirect } from 'expo-router';
import { ProtectedRouteGate } from './ProtectedRouteGate';
import { useAuth } from '../../context/AuthContext';
import { useAccessControl } from '../../context/AccessControlContext';

type FeatureRouteGateProps = {
  /** Route path used for the plan/tier access decision (e.g. '/features/video-studio'). */
  path: string;
  /** Where to return after sign-in. Defaults to `path`. */
  returnTo?: string;
  children: React.ReactNode;
};

/**
 * Standard protected-route wrapper for feature pages.
 * Combines the auth contract (ProtectedRouteGate) with the unified
 * plan/tier decision from AccessControlContext.canAccessRoute.
 */
export function FeatureRouteGate({ path, returnTo, children }: FeatureRouteGateProps) {
  const { isAuthenticated, loading } = useAuth();
  const { canAccessRoute, loading: aclLoading } = useAccessControl();
  const decision = canAccessRoute(path);

  return (
    <ProtectedRouteGate isLoading={loading || aclLoading} isAllowed={isAuthenticated} returnTo={returnTo || path}>
      {decision.allowed ? <>{children}</> : <Redirect href={(decision.redirectTo || '/subscription/plans') as any} />}
    </ProtectedRouteGate>
  );
}
