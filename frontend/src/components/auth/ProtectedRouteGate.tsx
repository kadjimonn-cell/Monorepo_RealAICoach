import React, { useEffect, useMemo, useState } from 'react';
import { Redirect } from 'expo-router';
import { SecureSessionLoadingScreen } from './SecureSessionLoadingScreen';
import { buildWelcomeAuthRedirect } from '../../utils/authRedirect';
import { useAuth } from '../../context/AuthContext';
import type { ServerSessionProbeResult } from '../../context/auth/types';
import { useLanguage } from '../../i18n/LanguageContext';

type ServerSessionGateState = 'idle' | 'verifying' | 'verified' | 'blocked';

type ProtectedRouteGateProps = {
  isLoading?: boolean;
  isAllowed?: boolean;
  returnTo: string;
  children: React.ReactNode;
  requireFreshServerSession?: boolean;
};

export function ProtectedRouteGate({
  isLoading = false,
  isAllowed = false,
  returnTo,
  children,
  requireFreshServerSession = false,
}: ProtectedRouteGateProps) {
  const { t } = useLanguage();
  const { probeServerSession, refreshUser } = useAuth();
  const [serverSessionGateState, setServerSessionGateState] = useState<ServerSessionGateState>('idle');
  const shouldVerifyServerSession = useMemo(
    () => requireFreshServerSession && !isLoading && isAllowed,
    [requireFreshServerSession, isLoading, isAllowed],
  );

  useEffect(() => {
    let cancelled = false;

    if (!shouldVerifyServerSession) {
      setServerSessionGateState('idle');
      return () => {
        cancelled = true;
      };
    }

    setServerSessionGateState('verifying');

    const resolveFreshServerSession = async () => {
      const finalizeFromProbe = async (probe: ServerSessionProbeResult) => {
        if (probe.state === 'authenticated') {
          if (!cancelled) {
            setServerSessionGateState('verified');
          }
          return true;
        }

        try {
          await refreshUser();
        } catch {
          // best-effort session reconciliation
        }

        if (cancelled) {
          return true;
        }

        return false;
      };

      const firstProbe = await probeServerSession();
      const firstResolved = await finalizeFromProbe(firstProbe);
      if (firstResolved) {
        return;
      }

      const secondProbe = await probeServerSession();
      if (secondProbe.state === 'authenticated') {
        if (!cancelled) {
          setServerSessionGateState('verified');
        }
        return;
      }

      if (!cancelled) {
        setServerSessionGateState('blocked');
      }
    };

    void resolveFreshServerSession();

    return () => {
      cancelled = true;
    };
  }, [probeServerSession, refreshUser, shouldVerifyServerSession, returnTo]);

  if (isLoading) {
    return <SecureSessionLoadingScreen />;
  }

  if (shouldVerifyServerSession && serverSessionGateState !== 'verified') {
    if (serverSessionGateState === 'blocked') {
      return <Redirect href={buildWelcomeAuthRedirect(returnTo, 'unauthenticated')} />;
    }

    return (
      <SecureSessionLoadingScreen
        title={t('authGate.checkingSession')}
        message={t('authGate.confirmDashboardAccess')}
      />
    );
  }

  if (!isAllowed) {
    return <Redirect href={buildWelcomeAuthRedirect(returnTo, 'unauthenticated')} />;
  }

  return <>{children}</>;
}