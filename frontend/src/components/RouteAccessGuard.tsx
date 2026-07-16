import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { usePathname, useRouter } from 'expo-router';
import { useAccessControl } from '../context/AccessControlContext';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { hasKnownTopLevelSegment, normalizeIncomingSystemPath } from '../utils/routeResolution';
import { getUpgradeCopyForPath } from '../utils/routeUpgradeCopy';
import { getBackendOriginConsistency, normalizeBaseUrl, resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { resolveVisitorCtaPath } from '../utils/visitorCtaPolicy';
import { buildWelcomeAuthRedirect } from '../utils/authRedirect';

const PUBLIC_EXACT_ROUTES = new Set([
  '/',
  '/welcome',
  '/about',
  '/contact',
  '/pricing',
  '/auth',
  '/about-us',
  '/talent-network',
  '/careers',
  '/career',
  '/blog',
  '/feature-gallery',
  '/features',
  '/track-application',
  '/press',
  '/privacy-policy',
  '/privacy-request',
  '/terms',
  '/security',
  '/gdpr',
  '/cookies',
  '/fps-match',
  '/certificate-verify',
]);
const PUBLIC_PREFIXES = ['/auth/', '/careers/', '/blog/', '/press', '/fps-match/', '/certificate-verify/'];
const TELEMETRY_COOLDOWN_MS = 60_000;
const TRANSIENT_AUTH_GRACE_MS = 4500;
const ACCESS_LOADING_FAILSAFE_MS = 6500;
const AUTHENTICATED_ACCESS_OVERLAY_DELAY_MS = 350;
const AUTHENTICATED_ACCESS_SOFT_RELEASE_MS = 1800;
const ENABLE_P0_AUTH_GUARD_HARDENING = String(process.env.REACT_APP_ENABLE_AUTH_GUARD_P0_HARDENING || 'true').toLowerCase() === 'true';
const ENABLE_P1_AUTH_CANONICAL_ORIGIN_RECOVERY = String(process.env.REACT_APP_ENABLE_AUTH_CANONICAL_ORIGIN_RECOVERY || 'true').toLowerCase() === 'true';
const ENABLE_P1_AUTH_PRELOGIN_RECOVERY = String(process.env.REACT_APP_ENABLE_AUTH_PRELOGIN_RECOVERY_FLOW || 'true').toLowerCase() === 'true';
const ENABLE_STRICT_WELCOME_LOCK_UNAUTH = String(process.env.REACT_APP_STRICT_WELCOME_LOCK_UNAUTH || 'true').toLowerCase() === 'true';
const CANONICAL_ORIGIN_REDIRECT_COOLDOWN_MS = 90_000;
const ORIGIN_RECOVERY_QUERY_KEY = 'origin_recover';
const INTENDED_ROUTE_KEY = 'rac:last-intended-route';
const INTENDED_ROUTE_TS_KEY = 'rac:last-intended-route-ts';
const INTENDED_ROUTE_ATTEMPTS_KEY = 'rac:last-intended-route-attempts';
const AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY = 'rac:auth-entry-replay-skip-until';
const TRANSIENT_PROBE_RETRY_FAILSAFE_MS = 9000;
const BACKEND_ORIGIN_CONSISTENCY = getBackendOriginConsistency();
const CANONICAL_AUTH_ORIGIN = normalizeBaseUrl(BACKEND_ORIGIN_CONSISTENCY.canonicalBase || '');
const BACKEND_BASE = normalizeBaseUrl(resolveRuntimeBaseUrl()).replace(/\/+$/, '');

type OverlayTone = 'neutral' | 'polished';

type OverlayState = {
  title: string;
  body: string;
  tone?: OverlayTone;
  recommendedPlan?: 'basic' | 'premium';
  currentPlan?: string;
};

function getAuthenticatedTransitionCopy(pathname: string): { title: string; body: string } {
  const normalized = stripPathDecorators(pathname || '/');

  if (normalized === '/dashboard' || normalized === '/home' || normalized === '/(tabs)' || normalized === '/') {
    return {
      title: 'Almost to your dashboard',
      body: 'Syncing your dashboard access for a smooth handoff.',
    };
  }

  if (normalized === '/profile' || normalized.startsWith('/edit-profile')) {
    return {
      title: 'Almost to your profile',
      body: 'Pulling your profile workspace into place.',
    };
  }

  if (normalized === '/features' || normalized.startsWith('/features/')) {
    return {
      title: 'Almost to your features',
      body: 'Syncing feature access so the right tools are ready for you.',
    };
  }

  if (normalized === '/book-meeting' || normalized.startsWith('/book/')) {
    return {
      title: 'Almost to your booking space',
      body: 'Preparing your meeting workspace and access details.',
    };
  }

  if (normalized.startsWith('/subscription/')) {
    return {
      title: 'Almost to your plan details',
      body: 'Syncing your subscription access and next options.',
    };
  }

  return {
    title: 'Almost there',
    body: 'Syncing your workspace access for a smooth handoff.',
  };
}

function getUpgradeContextLabel(pathname: string): string {
  const normalized = stripPathDecorators(pathname || '/');

  if (normalized === '/dashboard' || normalized === '/home' || normalized === '/(tabs)' || normalized === '/') {
    return 'dashboard';
  }

  if (normalized === '/profile' || normalized.startsWith('/edit-profile')) {
    return 'profile';
  }

  if (normalized === '/features' || normalized.startsWith('/features/')) {
    return 'features';
  }

  if (normalized === '/book-meeting' || normalized.startsWith('/book/')) {
    return 'booking space';
  }

  if (normalized.startsWith('/subscription/')) {
    return 'plan options';
  }

  return 'workspace';
}

function isSubscriptionBlock(reason: string | undefined): boolean {
  return reason === 'basic_required' || reason === 'premium_required' || reason === 'free_limited_access';
}

type SubscriptionGateContext = {
  decision: { allowed: boolean; reason?: string; message?: string; redirectTo?: string };
  accessPath: string;
  currentPlan: string;
  upgradeOverlayLockedRef: React.MutableRefObject<boolean>;
  setOverlayState: (state: OverlayState | null) => void;
  router: ReturnType<typeof useRouter>;
};

/**
 * Shared handler for subscription-gated redirects.
 * Computes upgrade copy, sets the upgrade badge overlay, locks it from being
 * cleared by effect re-runs, and schedules the deferred redirect.
 * Returns true if the redirect was handled (caller should return).
 */
function handleSubscriptionGatedRedirect(ctx: SubscriptionGateContext): boolean {
  const { decision, accessPath, currentPlan, upgradeOverlayLockedRef, setOverlayState, router } = ctx;
  const upgradeTitle = isSubscriptionBlock(decision.reason);
  const upgradeCopy = getUpgradeCopyForPath(accessPath);
  const title = upgradeTitle ? upgradeCopy.title : 'Access restricted';
  const body = upgradeTitle
    ? `${upgradeCopy.benefit} ${upgradeCopy.cta} to continue.`
    : (decision.message || 'Redirecting you to an allowed page.');

  if (upgradeTitle) {
    upgradeOverlayLockedRef.current = true;
  }

  setOverlayState({
    title,
    body,
    recommendedPlan: upgradeTitle ? upgradeCopy.recommendedPlan : undefined,
    currentPlan: upgradeTitle ? currentPlan : undefined,
  });

  const target = String(decision.redirectTo || '/dashboard');
  const doReplace = (href: string) => {
    upgradeOverlayLockedRef.current = false;
    router.replace(href as any);
  };

  if (target.startsWith('/subscription/plans')) {
    const pathParam = encodeURIComponent(accessPath || '/');
    const reasonParam = encodeURIComponent(String(decision.reason || 'subscription_required'));
    const planParam = encodeURIComponent(upgradeCopy.recommendedPlan);
    const contextParam = encodeURIComponent(getUpgradeContextLabel(accessPath));
    const titleParam = encodeURIComponent(upgradeCopy.title);
    const upgradeHref = `/subscription/plans?upgrade_from=${pathParam}&upgrade_reason=${reasonParam}&recommended_plan=${planParam}&upgrade_context=${contextParam}&upgrade_title=${titleParam}`;
    if (upgradeTitle) {
      setTimeout(() => doReplace(upgradeHref), 800);
    } else {
      doReplace(upgradeHref);
    }
    return true;
  }

  doReplace(target);
  return true;
}

function stripPathDecorators(pathname: string): string {
  return (
    normalizeIncomingSystemPath(pathname || '/')
      .split(/[?#]/)[0]
      .replace(/\/+$/, '')
  ) || '/';
}

function getSingleQueryParam(raw: string | string[] | undefined): string {
  if (Array.isArray(raw)) return String(raw[0] || '').trim();
  return String(raw || '').trim();
}

function getUrlQueryParam(param: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return String(new URLSearchParams(window.location.search || '').get(param) || '').trim();
  } catch {
    return '';
  }
}

function isTrustedCanonicalSwitch(currentOrigin: string, targetOrigin: string): boolean {
  if (!currentOrigin || !targetOrigin || currentOrigin === targetOrigin) return false;
  try {
    const currentHost = new URL(currentOrigin).host.toLowerCase();
    const targetHost = new URL(targetOrigin).host.toLowerCase();
    const trustedSuffixes = ['.emergentagent.com', '.emergent.sh'];
    const suffixTrusted = trustedSuffixes.some((suffix) => currentHost.endsWith(suffix) && targetHost.endsWith(suffix));
    if (suffixTrusted) return true;

    const currentParts = currentHost.split('.');
    const targetParts = targetHost.split('.');
    if (currentParts.length < 2 || targetParts.length < 2) return false;
    return currentParts.slice(-2).join('.') === targetParts.slice(-2).join('.');
  } catch {
    return false;
  }
}

function isPublicRoute(pathname: string) {
  const normalized = stripPathDecorators(pathname || '/');
  return PUBLIC_EXACT_ROUTES.has(normalized) || PUBLIC_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

function isAuthRoute(pathname: string): boolean {
  const normalized = stripPathDecorators(pathname || '/');
  return normalized === '/auth' || normalized.startsWith('/auth/');
}

function hasSessionRecoveryHint(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const snapshot = window.localStorage.getItem('auth_user_snapshot');
    return Boolean(snapshot && snapshot.length > 4);
  } catch {
    return false;
  }
}

function clearStickyReplayRouteState() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(INTENDED_ROUTE_KEY);
    window.sessionStorage.removeItem(INTENDED_ROUTE_TS_KEY);
    window.sessionStorage.removeItem(INTENDED_ROUTE_ATTEMPTS_KEY);
  } catch {
    // no-op
  }
}

export default function RouteAccessGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading: authLoading, refreshUser, hasServerSession, probeServerSession } = useAuth();
  const { loading: accessLoading, canAccessRoute, effectivePlan: acEffectivePlan } = useAccessControl();
  const lastBlockedPath = useRef<string>('');
  const unauthGraceStartedAtRef = useRef<number>(0);
  const recoveryRefreshAttemptedRef = useRef<Record<string, boolean>>({});
  const telemetryCooldownMap = useRef<Record<string, number>>({});
  const strictProbeInFlightRef = useRef<Record<string, boolean>>({});
  const preLoginRecoveryInFlightRef = useRef<Record<string, boolean>>({});
  const strictRecoveryReasonRef = useRef<Record<string, string>>({});
  const canonicalRedirectAttemptRef = useRef<Record<string, number>>({});
  const [overlayState, setOverlayState] = useState<OverlayState | null>(null);
  const [guardRecoveryVersion, setGuardRecoveryVersion] = useState(0);
  const accessLoadingStartedAtRef = useRef<number>(0);
  const accessOverlayDelayStartedAtRef = useRef<number>(0);
  const transientProbeRetryStartedAtRef = useRef<Record<string, number>>({});
  const upgradeOverlayLockedRef = useRef<boolean>(false);

  const emitBlockTelemetry = (blockedPath: string, reason: string) => {
    const key = `${reason}:${blockedPath}`;
    const now = Date.now();
    const last = telemetryCooldownMap.current[key] || 0;
    if (now - last < TELEMETRY_COOLDOWN_MS) return;
    telemetryCooldownMap.current[key] = now;

    if (typeof fetch !== 'function') return;

    const referrer = typeof document !== 'undefined' ? (document.referrer || '') : '';
    fetch(BACKEND_BASE ? `${BACKEND_BASE}/api/auth-compliance/route-block` : '/api/auth-compliance/route-block', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path: blockedPath,
        reason,
        source: 'frontend-route-guard',
        referrer,
      }),
      keepalive: true,
      credentials: 'include',
    }).catch(() => {
      // best-effort compliance telemetry
    });
  };

  const emitRecoveryTelemetry = (reasonCode: string, extra: Record<string, any> = {}) => {
    const now = Date.now();
    const key = `recovery:${reasonCode}:${extra.phase || 'route_guard'}`;
    const last = telemetryCooldownMap.current[key] || 0;
    if (now - last < 10_000) return;
    telemetryCooldownMap.current[key] = now;

    if (typeof window !== 'undefined') {
      try {
        window.dispatchEvent(new CustomEvent('auth-session-telemetry', {
          detail: {
            reason_code: reasonCode,
            phase: extra.phase || 'route_guard',
            timestamp: new Date().toISOString(),
            ...extra,
          },
        }));
      } catch {
        // best effort event bridge
      }
    }

    if (typeof fetch !== 'function') return;
    fetch(BACKEND_BASE ? `${BACKEND_BASE}/api/auth/session-bootstrap-telemetry` : '/api/auth/session-bootstrap-telemetry', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        reason_code: reasonCode,
        phase: extra.phase || 'route_guard',
        status: typeof extra.status === 'number' ? extra.status : undefined,
        attempt: typeof extra.attempt === 'number' ? extra.attempt : undefined,
      }),
      keepalive: true,
      credentials: 'include',
    }).catch(() => {
      // unauthenticated paths can fail by design
    });
  };

  useEffect(() => {
    if (!pathname) return;
    const normalizedPathname = normalizeIncomingSystemPath(pathname || '/');
    const browserPathname = typeof window !== 'undefined'
      ? normalizeIncomingSystemPath(window.location.pathname || normalizedPathname)
      : normalizedPathname;
    const bootstrapPathname = (
      normalizedPathname === '/+not-found' || normalizedPathname === '/404'
    )
      ? browserPathname
      : normalizedPathname;

    let replaySkipUntilTs = 0;
    if (typeof window !== 'undefined') {
      try {
        replaySkipUntilTs = Number(window.sessionStorage.getItem(AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY) || '0');
        if (Number.isFinite(replaySkipUntilTs) && replaySkipUntilTs > 0 && Date.now() >= replaySkipUntilTs) {
          window.sessionStorage.removeItem(AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY);
          replaySkipUntilTs = 0;
        }
      } catch {
        replaySkipUntilTs = 0;
      }
    }
    const replaySkipActive = Boolean(Number.isFinite(replaySkipUntilTs) && replaySkipUntilTs > Date.now());
    const bootstrapPathnameClean = stripPathDecorators(bootstrapPathname || '/');
    const normalizedPathnameClean = stripPathDecorators(normalizedPathname || '/');
    const browserPathnameClean = stripPathDecorators(browserPathname || '/');
    const shouldBypassPublicGuard = isPublicRoute(bootstrapPathnameClean)
      || isPublicRoute(normalizedPathnameClean)
      || isPublicRoute(browserPathnameClean);

    if (shouldBypassPublicGuard) {
      accessLoadingStartedAtRef.current = 0;
      accessOverlayDelayStartedAtRef.current = 0;
      if (!upgradeOverlayLockedRef.current) {
        setOverlayState(null);
      }
      return;
    }

    if (typeof window !== 'undefined' && user && !authLoading && !accessLoading && !replaySkipActive) {
      try {
        const intendedRoute = normalizeIncomingSystemPath(window.sessionStorage.getItem(INTENDED_ROUTE_KEY) || '');
        const intendedTs = Number(window.sessionStorage.getItem(INTENDED_ROUTE_TS_KEY) || '0');
        const attempts = Number(window.sessionStorage.getItem(INTENDED_ROUTE_ATTEMPTS_KEY) || '0');
        const ageMs = Date.now() - intendedTs;
        const currentIsFallback =
          normalizedPathname === '/' ||
          normalizedPathname === '/welcome' ||
          normalizedPathname === '/dashboard' ||
          normalizedPathname === '/(tabs)';
        const intendedIsFeature = intendedRoute === '/features' || intendedRoute.startsWith('/features/');
        const intendedDecision = intendedRoute ? canAccessRoute(intendedRoute) : { allowed: false };
        const intendedAccessible = Boolean(intendedDecision?.allowed);

        if (!intendedAccessible && intendedIsFeature) {
          clearStickyReplayRouteState();
        }

        if (
          currentIsFallback
          && intendedIsFeature
          && intendedAccessible
          && ageMs < 20000
          && attempts < 6
          && intendedRoute !== normalizedPathname
        ) {
          window.sessionStorage.setItem(INTENDED_ROUTE_ATTEMPTS_KEY, String(attempts + 1));
          router.replace(intendedRoute as any);
          return;
        }
      } catch {
        // no-op
      }
    }

    if (!isPublicRoute(bootstrapPathname) && (authLoading || accessLoading)) {
      // If upgrade overlay is locked, don't let accessLoading branch overwrite it
      if (upgradeOverlayLockedRef.current) {
        return;
      }

      // ── EAGER SUBSCRIPTION-GATE SHORT-CIRCUIT ──
      // When the user is authenticated but accessLoading is still true (session
      // API in-flight), evaluate canAccessRoute() eagerly using available user
      // data. If the route is clearly subscription-gated (basic_required,
      // premium_required, free_limited_access), skip the loading wait and
      // proceed directly to the upgrade badge + redirect flow. This eliminates
      // the ~4.8s accessLoading dwell time for subscription-blocked routes.
      // Safe because: subscription prefix matching is fully client-side and
      // user.subscription_plan is already known from AuthContext.
      if (user && !authLoading && accessLoading) {
        const eagerAccessPath = (
          normalizeIncomingSystemPath(bootstrapPathname || '/')
            .split(/[?#]/)[0]
            .replace(/\/+$/, '')
        ) || '/';
        const eagerDecision = canAccessRoute(eagerAccessPath);
        const isEagerSubscriptionBlock =
          isSubscriptionBlock(eagerDecision?.reason);

        if (!eagerDecision.allowed && isEagerSubscriptionBlock) {
          // Short-circuit: don't wait for session — proceed to upgrade badge
          accessLoadingStartedAtRef.current = 0;
          accessOverlayDelayStartedAtRef.current = 0;
          // Fall through to the main guard logic below (do NOT return)
        } else {
          // Not a clear subscription block — continue with normal loading flow
          const now = Date.now();
          if (!accessLoadingStartedAtRef.current) {
            accessLoadingStartedAtRef.current = now;
          }
          if (!accessOverlayDelayStartedAtRef.current) {
            accessOverlayDelayStartedAtRef.current = now;
          }

          const elapsed = now - accessLoadingStartedAtRef.current;
          if (elapsed > ACCESS_LOADING_FAILSAFE_MS) {
            setOverlayState(null);
            emitRecoveryTelemetry('access_loading_failsafe_released', {
              phase: 'route_guard',
              path: bootstrapPathname,
              elapsed_ms: elapsed,
            });
            // Fall through so canAccessRoute() runs with available data.
          } else {
            const authenticatedTransitionCopy = getAuthenticatedTransitionCopy(bootstrapPathname);
            const authenticatedAccessOverlayElapsed = now - Number(accessOverlayDelayStartedAtRef.current || now);
          if (authenticatedAccessOverlayElapsed > AUTHENTICATED_ACCESS_SOFT_RELEASE_MS) {
            setOverlayState(null);
            emitRecoveryTelemetry('authenticated_access_soft_released', {
              phase: 'route_guard',
              path: bootstrapPathname,
              elapsed_ms: authenticatedAccessOverlayElapsed,
            });
            return;
          }
            if (authenticatedAccessOverlayElapsed < AUTHENTICATED_ACCESS_OVERLAY_DELAY_MS) {
              setOverlayState(null);
              return;
            }
            setOverlayState({
              title: authenticatedTransitionCopy.title,
              body: authenticatedTransitionCopy.body,
              tone: 'polished',
            });
            return;
          }
        }
      } else if (authLoading) {
        // Auth still loading — show generic loading overlay
        const now = Date.now();
        if (!accessLoadingStartedAtRef.current) {
          accessLoadingStartedAtRef.current = now;
        }
        setOverlayState({
          title: 'Checking access',
          body: 'Please wait while we prepare this page.',
          tone: 'neutral',
        });
        return;
      }
    }

    accessLoadingStartedAtRef.current = 0;
    accessOverlayDelayStartedAtRef.current = 0;

    // Don't clear overlay if upgrade badge is locked (waiting for deferred redirect)
    if (!upgradeOverlayLockedRef.current) {
      setOverlayState(null);
    }

    if (authLoading || accessLoading) return;

    // Guard against false-positive "unknown route" redirects. On hard
    // refreshes of routes whose JS bundles haven't loaded yet, Expo Router
    // transiently renders `+not-found` and `usePathname()` briefly returns
    // `/+not-found` BEFORE the real route mounts. If we eagerly
    // `router.replace('/')` from here, the user's refresh of e.g.
    // `/book-meeting` drifts all the way back to the Home dashboard
    // (because `/` -> app/index.tsx -> /dashboard -> /(tabs)). Instead,
    // trust `window.location.pathname` (which reflects the URL the user
    // actually requested) when the router-reported pathname looks like
    // a transient not-found — and only redirect if the REAL URL also
    // has no known segment. `+not-found` itself has its own self-cancelling
    // 5-second countdown (see `/app/frontend/app/+not-found.tsx`) so
    // legitimate 404s still resolve cleanly.
    const routerPath = normalizeIncomingSystemPath(pathname || '/');
    const realPath = normalizeIncomingSystemPath(((typeof window !== 'undefined' && window.location?.pathname) || pathname || '/') as string);
    const routerSaysNotFound =
      routerPath === '/+not-found' ||
      routerPath === '/404' ||
      realPath === '/+not-found' ||
      realPath === '/404';
    const effectivePath = hasKnownTopLevelSegment(realPath) ? realPath : routerPath;

    const rawSearch = (() => {
      if (typeof window !== 'undefined' && typeof window.location?.search === 'string') {
        return window.location.search;
      }
      try {
        const routerHref = (router as any)?.asPath || '';
        const hrefText = String(routerHref || '');
        const idx = hrefText.indexOf('?');
        return idx >= 0 ? hrefText.slice(idx) : '';
      } catch {
        return '';
      }
    })();
    const searchParams = new URLSearchParams(rawSearch || '');
    const flowSource = getSingleQueryParam(searchParams.get('source') || '');
    const upgradeFrom = getSingleQueryParam(searchParams.get('upgrade_from') || '');

    const isSubscriptionPlansPath = stripPathDecorators(effectivePath) === '/subscription/plans';
    const isCompareSource = flowSource === 'pricing-compare';
    const isUpgradeFromPricingSurface = upgradeFrom === '/pricing' || upgradeFrom === '/welcome' || upgradeFrom === '/welcome?section=pricing';

    if (isSubscriptionPlansPath && !user) {
      const normalizedPricingSurface = '/welcome?section=pricing';
      if (lastBlockedPath.current !== `normalize:${effectivePath}:pricing-public`) {
        lastBlockedPath.current = `normalize:${effectivePath}:pricing-public`;
        setOverlayState({ title: 'Redirecting', body: 'Taking you to pricing overview.' });
        router.replace(normalizedPricingSurface as any);
      }
      return;
    }

    if (isSubscriptionPlansPath && (isCompareSource || isUpgradeFromPricingSurface)) {
      const normalizedPricingSurface = '/welcome?section=pricing';
      if (lastBlockedPath.current !== `normalize:${effectivePath}:pricing`) {
        lastBlockedPath.current = `normalize:${effectivePath}:pricing`;
        setOverlayState({ title: 'Redirecting', body: 'Taking you to pricing overview.' });
        router.replace(normalizedPricingSurface as any);
      }
      return;
    }
    const realPathIsUnknown = !hasKnownTopLevelSegment(effectivePath);

    if (typeof window !== 'undefined') {
      try {
        const canStickRoute =
          Boolean(user)
          && !replaySkipActive
          && !!effectivePath &&
          effectivePath !== '/' &&
          effectivePath !== '/welcome' &&
          !effectivePath.startsWith('/auth/') &&
          hasKnownTopLevelSegment(effectivePath);

        if (canStickRoute) {
          const existing = window.sessionStorage.getItem(INTENDED_ROUTE_KEY) || '';
          if (existing !== effectivePath) {
            window.sessionStorage.setItem(INTENDED_ROUTE_ATTEMPTS_KEY, '0');
          }
          window.sessionStorage.setItem(INTENDED_ROUTE_KEY, effectivePath);
          window.sessionStorage.setItem(INTENDED_ROUTE_TS_KEY, String(Date.now()));
        } else if (!user && (effectivePath === '/welcome' || effectivePath.startsWith('/auth/'))) {
          clearStickyReplayRouteState();
        }
      } catch {
        // no-op
      }
    }

    // Strict visitor CTA policy: unauthenticated visitors should not be routed into auth surfaces
    // from welcome/footer CTA leakage. Keep direct auth routes available only when explicitly entered.
    if (!user) {
      const requestedPath = normalizeIncomingSystemPath(effectivePath || realPath || routerPath || '/');
      const sanitized = resolveVisitorCtaPath(requestedPath, {
        isAuthenticated: false,
        surface: 'public',
        fallbackPath: '/welcome',
      });

      if (sanitized !== requestedPath && !isAuthRoute(requestedPath)) {
        if (lastBlockedPath.current !== requestedPath) {
          lastBlockedPath.current = requestedPath;
          setOverlayState({ title: 'Redirecting', body: 'Taking you to the public welcome experience.' });
          router.replace('/welcome' as any);
        }
        return;
      }
    }

    const effectivePathClean = stripPathDecorators(effectivePath || '/');
    const realPathClean = stripPathDecorators(realPath || '/');
    const routerPathClean = stripPathDecorators(routerPath || '/');

    // Check public routes FIRST before any redirect logic
    // This ensures /blog, /careers etc. remain accessible without auth
    if (isPublicRoute(effectivePathClean) || isPublicRoute(realPathClean) || isPublicRoute(routerPathClean)) {
      return;
    }

    // ── AUTHENTICATED USER FAST-PATH ──
    // Once a user is authenticated, auth flow NEVER interferes with navigation again.
    // Only subscription plan (Free/Basic/Premium) controls feature access.
    // This eliminates "double-auth" — no session probes, recovery overlays, or
    // re-verification for users who already have a valid session.
    if (user) {
      unauthGraceStartedAtRef.current = 0;
      recoveryRefreshAttemptedRef.current = {};
      transientProbeRetryStartedAtRef.current = {};

      const accessPath = (
        normalizeIncomingSystemPath(effectivePath || '/')
          .split(/[?#]/)[0]
          .replace(/\/+$/, '')
      ) || '/';
      const decision = canAccessRoute(accessPath);
      if (decision.allowed) {
        lastBlockedPath.current = '';
        return;
      }
      if (lastBlockedPath.current === effectivePath) return;

      emitBlockTelemetry(
        effectivePath,
        decision?.reason ? `permission_denied_route_block:${decision.reason}` : 'permission_denied_route_block',
      );
      lastBlockedPath.current = effectivePath;
      handleSubscriptionGatedRedirect({
        decision,
        accessPath,
        currentPlan: acEffectivePlan || 'free',
        upgradeOverlayLockedRef,
        setOverlayState,
        router,
      });
      return;
    }
    // ── END AUTHENTICATED USER FAST-PATH ──

    const unresolvedOrShortLink =
      routerSaysNotFound
      || realPath.startsWith('/s/')
      || routerPath.startsWith('/s/');

    if (unresolvedOrShortLink || realPathIsUnknown) {
      // Even if router says not-found, if the real browser path is a public route, allow it
      // This handles the case where Expo Router hasn't resolved the dynamic route yet
      if (isPublicRoute(realPath)) {
        return;
      }
      if (!user) {
        const blockedPath = normalizeIncomingSystemPath(realPath || routerPath || '/');
        emitBlockTelemetry(blockedPath, 'unauthenticated_unresolved_route_block');
        if (lastBlockedPath.current !== blockedPath) {
          lastBlockedPath.current = blockedPath;
          setOverlayState({ title: 'Sign in required', body: 'Redirecting you to the welcome page.' });
          router.replace(buildWelcomeAuthRedirect(blockedPath, 'unauthenticated') as any);
        }
      }
      return;
    }

    if (!user && ENABLE_STRICT_WELCOME_LOCK_UNAUTH && !isPublicRoute(effectivePathClean)) {
      const blockedPath = normalizeIncomingSystemPath(effectivePath || '/');
      emitBlockTelemetry(blockedPath, 'strict_welcome_lock_unauthenticated');
      if (lastBlockedPath.current !== blockedPath) {
        lastBlockedPath.current = blockedPath;
        setOverlayState({ title: 'Sign in required', body: 'Redirecting you to the welcome page.' });
        router.replace(buildWelcomeAuthRedirect(blockedPath, 'unauthenticated') as any);
      }
      return;
    }

    const originRecoveryHint = getUrlQueryParam(ORIGIN_RECOVERY_QUERY_KEY) === '1';

    if (user && originRecoveryHint && typeof window !== 'undefined') {
      try {
        const params = new URLSearchParams(window.location.search || '');
        params.delete(ORIGIN_RECOVERY_QUERY_KEY);
        const nextQs = params.toString();
        window.history.replaceState(null, '', `${effectivePath}${nextQs ? `?${nextQs}` : ''}`);
      } catch {
        // non-critical
      }
    }

    if (
      !user
      && ENABLE_P1_AUTH_CANONICAL_ORIGIN_RECOVERY
      && BACKEND_ORIGIN_CONSISTENCY.ok
      && typeof window !== 'undefined'
    ) {
      const currentOrigin = normalizeBaseUrl(window.location.origin || '');
      const targetOrigin = CANONICAL_AUTH_ORIGIN;
      const shouldRedirectToCanonical = isTrustedCanonicalSwitch(currentOrigin, targetOrigin);

      if (shouldRedirectToCanonical && !originRecoveryHint) {
        const key = `${effectivePath}:${targetOrigin}`;
        const now = Date.now();
        let lastAttempt = canonicalRedirectAttemptRef.current[key] || 0;
        try {
          const persisted = Number(window.sessionStorage.getItem(`rac:canonical-recovery:${key}`) || '0');
          if (Number.isFinite(persisted) && persisted > 0) {
            lastAttempt = Math.max(lastAttempt, persisted);
          }
        } catch {
          // no-op
        }

        if (!lastAttempt || now - lastAttempt > CANONICAL_ORIGIN_REDIRECT_COOLDOWN_MS) {
          canonicalRedirectAttemptRef.current[key] = now;
          try {
            window.sessionStorage.setItem(`rac:canonical-recovery:${key}`, String(now));
          } catch {
            // no-op
          }

          emitBlockTelemetry(effectivePath, 'canonical_origin_mismatch');
          emitRecoveryTelemetry('canonical_origin_mismatch_detected', { phase: 'route_guard', path: effectivePath });
          emitRecoveryTelemetry('canonical_origin_redirect_applied', { phase: 'route_guard', path: effectivePath });
          setOverlayState({ title: 'Aligning secure session', body: 'Switching to canonical platform origin for session recovery.' });

          try {
            const params = new URLSearchParams(window.location.search || '');
            params.set(ORIGIN_RECOVERY_QUERY_KEY, '1');
            const nextQs = params.toString();
            const canonicalTarget = `${targetOrigin}${effectivePath}${nextQs ? `?${nextQs}` : ''}`;
            window.location.replace(canonicalTarget);
            return;
          } catch {
            // fallback to regular flow
          }
        }
      }
    }

    const strictProtectedFeaturePath = effectivePath.startsWith('/features/');
    if (strictProtectedFeaturePath && !user) {
      const now = Date.now();
      if (!unauthGraceStartedAtRef.current) {
        unauthGraceStartedAtRef.current = now;
      }
      const elapsed = now - unauthGraceStartedAtRef.current;

      if (!strictProbeInFlightRef.current[effectivePath]) {
        strictProbeInFlightRef.current[effectivePath] = true;
        setOverlayState({ title: 'Verifying session', body: 'Confirming secure access to this feature.' });
        const strictProbeTask = ENABLE_P0_AUTH_GUARD_HARDENING
          ? probeServerSession().then((probe) => ({
            isAuthenticated: probe.state === 'authenticated',
            isTransient: probe.state === 'transient',
          }))
          : hasServerSession().then((isAuthenticated) => ({
            isAuthenticated,
            isTransient: false,
          }));

        void strictProbeTask
          .then(async ({ isAuthenticated, isTransient }) => {
            if (isAuthenticated) {
              unauthGraceStartedAtRef.current = 0;
              lastBlockedPath.current = '';
              strictRecoveryReasonRef.current[effectivePath] = '';
              emitRecoveryTelemetry('prelogin_recovery_success', { phase: 'route_guard_strict_probe' });
              return;
            }

            const hadRecoveryHint = hasSessionRecoveryHint() || originRecoveryHint;

            if (
              ENABLE_P1_AUTH_PRELOGIN_RECOVERY
              && hadRecoveryHint
              && !preLoginRecoveryInFlightRef.current[effectivePath]
            ) {
              preLoginRecoveryInFlightRef.current[effectivePath] = true;
              setOverlayState({ title: 'Restoring session', body: 'Trying secure session recovery before sign-in redirect.' });
              emitRecoveryTelemetry('prelogin_recovery_attempt', { phase: 'route_guard_strict_probe' });

              try {
                await refreshUser();
                const followupProbe = await probeServerSession();
                if (followupProbe.state === 'authenticated') {
                  strictRecoveryReasonRef.current[effectivePath] = '';
                  unauthGraceStartedAtRef.current = 0;
                  lastBlockedPath.current = '';
                  emitRecoveryTelemetry('prelogin_recovery_success', { phase: 'route_guard_strict_probe' });
                  return;
                }

                if (followupProbe.state === 'transient') {
                  emitRecoveryTelemetry('prelogin_recovery_transient', {
                    phase: 'route_guard_strict_probe',
                    status: followupProbe.status,
                  });
                  setOverlayState({ title: 'Restoring session', body: 'Temporary auth check issue detected. Retrying automatically.' });
                  return;
                }

                strictRecoveryReasonRef.current[effectivePath] = originRecoveryHint
                  ? 'origin_mismatch_recovered'
                  : 'session_expired';
                emitRecoveryTelemetry('prelogin_recovery_unauthenticated', {
                  phase: 'route_guard_strict_probe',
                  status: followupProbe.status,
                });
              } catch {
                strictRecoveryReasonRef.current[effectivePath] = originRecoveryHint
                  ? 'origin_mismatch_recovered'
                  : 'session_expired';
              } finally {
                preLoginRecoveryInFlightRef.current[effectivePath] = false;
                setGuardRecoveryVersion((v) => v + 1);
              }
            }

            if (isTransient && ENABLE_P0_AUTH_GUARD_HARDENING) {
              emitRecoveryTelemetry('prelogin_recovery_transient', { phase: 'route_guard_strict_probe' });
              setOverlayState({ title: 'Restoring session', body: 'Temporary auth check issue detected. Retrying automatically.' });
              strictRecoveryReasonRef.current[effectivePath] = 'transient_probe_retry';
              return;
            }

            strictRecoveryReasonRef.current[effectivePath] = originRecoveryHint
              ? 'origin_mismatch_recovered'
              : (hadRecoveryHint ? 'session_expired' : 'unauthenticated');

            emitBlockTelemetry(effectivePath, `strict_feature_auth_required:${strictRecoveryReasonRef.current[effectivePath]}`);
            if (lastBlockedPath.current !== effectivePath) {
              lastBlockedPath.current = effectivePath;
              const reason = ENABLE_P0_AUTH_GUARD_HARDENING
                ? (strictRecoveryReasonRef.current[effectivePath] || 'unauthenticated')
                : 'legacy_redirect';
              router.replace(buildWelcomeAuthRedirect(effectivePath, reason) as any);
            }
          })
          .finally(() => {
            strictProbeInFlightRef.current[effectivePath] = false;
            setGuardRecoveryVersion((v) => v + 1);
          });
      }

      if (elapsed < TRANSIENT_AUTH_GRACE_MS) {
        return;
      }
    }

    if (user) {
      unauthGraceStartedAtRef.current = 0;
      recoveryRefreshAttemptedRef.current = {};
      transientProbeRetryStartedAtRef.current = {};
    }

    if (!user) {
      const isStrictHomeRoute = effectivePath === '/' || effectivePath === '/welcome';
      const recoveryHint = hasSessionRecoveryHint();
      const shouldAttemptRecovery = (recoveryHint || originRecoveryHint) && !isStrictHomeRoute;
      if (shouldAttemptRecovery) {
        const now = Date.now();
        if (!unauthGraceStartedAtRef.current) {
          unauthGraceStartedAtRef.current = now;
        }
        if (!recoveryRefreshAttemptedRef.current[effectivePath] && ENABLE_P1_AUTH_PRELOGIN_RECOVERY) {
          recoveryRefreshAttemptedRef.current[effectivePath] = true;
          preLoginRecoveryInFlightRef.current[effectivePath] = true;
          emitRecoveryTelemetry('prelogin_recovery_attempt', { phase: 'route_guard_general' });
          void refreshUser().finally(() => {
            preLoginRecoveryInFlightRef.current[effectivePath] = false;
            setGuardRecoveryVersion((v) => v + 1);
          });
        }

        if (preLoginRecoveryInFlightRef.current[effectivePath]) {
          setOverlayState({ title: 'Restoring session', body: 'Revalidating your secure session before redirecting.' });
          return;
        }

        const elapsed = now - unauthGraceStartedAtRef.current;
        if (elapsed < TRANSIENT_AUTH_GRACE_MS) {
          setOverlayState({ title: 'Restoring session', body: 'Revalidating your secure session before redirecting.' });
          return;
        }
      }

      const derivedReason = strictRecoveryReasonRef.current[effectivePath]
        || (originRecoveryHint
          ? 'origin_mismatch_recovered'
          : (recoveryHint ? 'session_expired' : 'unauthenticated'));

      if (derivedReason === 'transient_probe_retry') {
        const now = Date.now();
        if (!transientProbeRetryStartedAtRef.current[effectivePath]) {
          transientProbeRetryStartedAtRef.current[effectivePath] = now;
        }
        const elapsed = now - Number(transientProbeRetryStartedAtRef.current[effectivePath] || now);
        if (elapsed > TRANSIENT_PROBE_RETRY_FAILSAFE_MS) {
          delete transientProbeRetryStartedAtRef.current[effectivePath];
          strictRecoveryReasonRef.current[effectivePath] = '';
          clearStickyReplayRouteState();
          emitRecoveryTelemetry('transient_probe_retry_failsafe_redirect', {
            phase: 'route_guard',
            path: effectivePath,
            elapsed_ms: elapsed,
          });
          setOverlayState({ title: 'Session check timed out', body: 'Returning you to the welcome page.' });
          router.replace('/welcome' as any);
          return;
        }
        setOverlayState({ title: 'Restoring session', body: 'Retrying secure session validation.' });
        return;
      }

      delete transientProbeRetryStartedAtRef.current[effectivePath];

      emitBlockTelemetry(effectivePath, `${derivedReason}_route_block`);
      if (lastBlockedPath.current === effectivePath) return;
      lastBlockedPath.current = effectivePath;
      setOverlayState({ title: 'Sign in required', body: 'Redirecting you to the welcome page.' });
      const reason = ENABLE_P0_AUTH_GUARD_HARDENING ? derivedReason : 'legacy_redirect';
      router.replace(buildWelcomeAuthRedirect(effectivePath, reason) as any);
      return;
    }

    const accessPath = (
      normalizeIncomingSystemPath(effectivePath || '/')
        .split(/[?#]/)[0]
        .replace(/\/+$/, '')
    ) || '/';
    const decision = canAccessRoute(accessPath);
    if (decision.allowed) {
      lastBlockedPath.current = '';
      return;
    }
    if (lastBlockedPath.current === effectivePath) return;

    emitBlockTelemetry(
      effectivePath,
      decision?.reason ? `permission_denied_route_block:${decision.reason}` : 'permission_denied_route_block',
    );
    lastBlockedPath.current = effectivePath;
    handleSubscriptionGatedRedirect({
      decision,
      accessPath,
      currentPlan: acEffectivePlan || 'free',
      upgradeOverlayLockedRef,
      setOverlayState,
      router,
    });
  }, [pathname, authLoading, accessLoading, user, canAccessRoute, router, refreshUser, hasServerSession, probeServerSession, guardRecoveryVersion, acEffectivePlan]);

  const { colors } = useTheme();
  const overlayIsPolished = overlayState?.tone === 'polished';
  const overlayIsUpgrade = Boolean(overlayState?.recommendedPlan);

  if (!overlayState) return null;

  const upgradeBadgeColor = overlayState.recommendedPlan === 'premium' ? colors.warning : colors.primary;
  const upgradeBadgeLabel = overlayState.recommendedPlan === 'premium' ? 'PREMIUM REQUIRED' : 'BASIC REQUIRED';
  const currentPlanLabel = String(overlayState.currentPlan || 'free').charAt(0).toUpperCase() + String(overlayState.currentPlan || 'free').slice(1);

  return (
    <View
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: overlayIsPolished ? `${colors.bg}F2` : colors.bg,
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        zIndex: 1300,
      }}
      data-testid="route-access-guard-overlay"
      testID="route-access-guard-overlay"
    >
      <View
        style={{
          width: '100%',
          maxWidth: overlayIsUpgrade ? 400 : (overlayIsPolished ? 420 : 380),
          borderRadius: overlayIsUpgrade ? 24 : (overlayIsPolished ? 28 : 22),
          borderWidth: 1,
          borderColor: overlayIsUpgrade ? `${upgradeBadgeColor}33` : (overlayIsPolished ? colors.border : colors.borderMd),
          backgroundColor: colors.card,
          paddingHorizontal: 24,
          paddingVertical: overlayIsUpgrade ? 26 : (overlayIsPolished ? 28 : 24),
          alignItems: 'center',
          shadowColor: overlayIsUpgrade ? upgradeBadgeColor : (overlayIsPolished ? colors.text : 'transparent'),
          shadowOpacity: overlayIsUpgrade ? 0.12 : (overlayIsPolished ? 0.08 : 0),
          shadowRadius: overlayIsUpgrade ? 24 : (overlayIsPolished ? 22 : 0),
          shadowOffset: overlayIsUpgrade ? { width: 0, height: 8 } : (overlayIsPolished ? { width: 0, height: 10 } : { width: 0, height: 0 }),
        }}
      >
        {overlayIsUpgrade ? (
          <View
            style={{
              paddingHorizontal: 14,
              paddingVertical: 6,
              borderRadius: 999,
              backgroundColor: `${upgradeBadgeColor}18`,
              borderWidth: 1,
              borderColor: `${upgradeBadgeColor}30`,
              marginBottom: 16,
            }}
            data-testid="route-access-guard-upgrade-badge"
            testID="route-access-guard-upgrade-badge"
          >
            <Text style={{ color: upgradeBadgeColor, fontSize: 11, fontWeight: '800', letterSpacing: 1.0 }}>
              {upgradeBadgeLabel}
            </Text>
          </View>
        ) : (
          <ActivityIndicator size="small" color={colors.primary} />
        )}
        {overlayIsPolished ? (
          <View
            style={{
              marginTop: 16,
              paddingHorizontal: 12,
              paddingVertical: 6,
              borderRadius: 999,
              backgroundColor: colors.bgSoft,
            }}
            data-testid="route-access-guard-status-pill"
            testID="route-access-guard-status-pill"
          >
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', letterSpacing: 0.6 }}>
              CONTINUING YOUR SESSION
            </Text>
          </View>
        ) : null}
        <Text style={{ color: colors.text, fontSize: overlayIsPolished ? 22 : 20, fontWeight: '800', marginTop: overlayIsUpgrade ? 4 : 16, textAlign: 'center' }} data-testid="route-access-guard-title" testID="route-access-guard-title">{overlayState.title}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 13, lineHeight: 20, marginTop: 8, textAlign: 'center', maxWidth: 300 }} data-testid="route-access-guard-body" testID="route-access-guard-body">{overlayState.body}</Text>
        {overlayIsUpgrade && overlayState.currentPlan ? (
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              marginTop: 14,
              paddingHorizontal: 12,
              paddingVertical: 5,
              borderRadius: 8,
              backgroundColor: colors.bgSoft,
            }}
            data-testid="route-access-guard-current-plan"
            testID="route-access-guard-current-plan"
          >
            <Text style={{ color: colors.textMuted, fontSize: 12 }}>Your plan:</Text>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }}>{currentPlanLabel}</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
