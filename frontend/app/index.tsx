import React from 'react';
import { Redirect } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { getLastSidebarRoute } from '../src/hooks/useLastSidebarRoute';
import { useTranslation } from '../src/hooks/useTranslation';
import { hasKnownTopLevelSegment, normalizeIncomingSystemPath } from '../src/utils/routeResolution';

const INTENDED_ROUTE_KEY = 'rac:last-intended-route';
const INTENDED_ROUTE_TS_KEY = 'rac:last-intended-route-ts';
const INTENDED_ROUTE_ATTEMPTS_KEY = 'rac:last-intended-route-attempts';
const AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY = 'rac:auth-entry-replay-skip-until';

  // Root index — routes authenticated users back to the last sidebar
  // page they were on (persisted in localStorage by the AppShell), or
  // the Home dashboard if there's no saved route. Unauthenticated users
  // are redirected to login.
export default function Index() {
  const { t } = useTranslation();
  t('i18n.route.index.probe');
  const { isAuthenticated, loading } = useAuth();

  const getStickyRoute = () => {
    if (typeof window === 'undefined') return '';
    try {
      const replaySkipUntil = Number(window.sessionStorage.getItem(AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY) || '0');
      if (Number.isFinite(replaySkipUntil) && replaySkipUntil > Date.now()) return '';

      const intended = normalizeIncomingSystemPath(window.sessionStorage.getItem(INTENDED_ROUTE_KEY) || '');
      const intendedTs = Number(window.sessionStorage.getItem(INTENDED_ROUTE_TS_KEY) || '0');
      const attempts = Number(window.sessionStorage.getItem(INTENDED_ROUTE_ATTEMPTS_KEY) || '0');
      const ageMs = Date.now() - intendedTs;
      if (!intended || intended === '/' || !hasKnownTopLevelSegment(intended)) return '';
      if (ageMs > 15000) return '';
      if (attempts >= 3) return '';
      window.sessionStorage.setItem(INTENDED_ROUTE_ATTEMPTS_KEY, String(attempts + 1));
      return intended;
    } catch {
      return '';
    }
  };

  if (typeof window !== 'undefined') {
    const browserPath = normalizeIncomingSystemPath(window.location.pathname || '/');
    if (browserPath !== '/') {
      return null;
    }
  }

  if (loading) return null;

  if (!isAuthenticated) {
    return <Redirect href="/welcome" />;
  }

  if (typeof window !== 'undefined') {
    const stickyRoute = getStickyRoute();
    if (stickyRoute) {
      return <Redirect href={stickyRoute as any} />;
    }
  }

  // Restore the last sidebar route so a browser refresh (or opening
  // `/` in a new tab mid-session) doesn't dump the user on Home.
  // `getLastSidebarRoute` is already guarded against unknown segments
  // so a deleted/renamed route can't strand the user.
  const last = getLastSidebarRoute();
  if (last && last !== '/' && last !== '/dashboard') {
    return <Redirect href={last as any} />;
  }

  return <Redirect href="/dashboard" />;
}
