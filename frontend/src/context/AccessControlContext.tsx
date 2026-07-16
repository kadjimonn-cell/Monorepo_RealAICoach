import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from '../services/api';
import { useAuth } from './AuthContext';
import { normalizeIncomingSystemPath } from '../utils/routeResolution';
import { hasAdminConsoleVisibility } from '../utils/adminAccess';

type RoutePolicy = { prefix: string; permission: string };

type AccessSession = {
  effective_plan: 'free' | 'basic' | 'premium';
  subscription_access_profile?: 'limited' | 'almost_unlimited' | 'full_unlimited' | string;
  entitlement_engine?: string;
  actor_type: 'user' | 'employee' | 'admin';
  is_admin: boolean;
  platform_role?: string | null;
  employee_permissions: string[];
  feature_entitlements: Record<string, any>;
  ui_route_policies: RoutePolicy[];
  ui_tier_routes?: Record<string, string[]>;
};

type AccessDecision = {
  allowed: boolean;
  reason?: string;
  message?: string;
  redirectTo?: string;
};

type AccessControlContextType = {
  loading: boolean;
  session: AccessSession | null;
  effectivePlan: 'free' | 'basic' | 'premium';
  hasPermission: (permission: string) => boolean;
  canAccessRoute: (path: string) => AccessDecision;
  canAccessPlan: (requiredPlan: 'basic' | 'premium') => boolean;
  refresh: () => Promise<void>;
};

const AccessControlContext = createContext<AccessControlContextType | undefined>(undefined);

const PLAN_LEVEL: Record<string, number> = { free: 0, basic: 1, premium: 2 };
const BASIC_UI_PREFIXES = ['/features'];
const PREMIUM_UI_PREFIXES = ['/content-studio', '/workspace'];

// ── PLATFORM SUBSCRIPTION ACCESS CONTROL POLICY (2026-06.v3) ──
// Free  → Limited access to ALL 37 canonical features (daily action meters)
// Basic → Almost unlimited
// Premium → Full unlimited access
// Auto-enforced via the AI-driven entitlement system.
const FREE_TIER_FEATURE_PREFIXES = [
  '/features/ai-writer',
  '/features/assistant',
  '/features/ai-search',
  '/features/ai-automations',
  '/features/ai-cognitive',
  '/features/decision-coach',
  '/features/school-tutor',
  '/features/medimate',
  '/features/health-dashboard',
  '/features/fitness',
  '/features/pennypilot',
  '/features/smartbuy',
  '/features/travelpal',
  '/features/ai-found-love',
  '/features/smart-cars',
  '/features/buy-smart-home',
  '/features/ai-video',
  '/features/ai-photo',
  '/features/ai-speech',
  '/features/ai-enterprise',
  '/features/bill-generator',
  '/features/lexicon-intelligence',
  '/features/watch-videos',
  '/features/fps-game',
  '/features/travel-visa',
  '/features/daily-meditation',
  '/features/audio-studio',
  '/features/my-podcasts',
  '/features/sports',
  '/features/flappy-bird',
  '/features/ai-chatbot',
];
const PUBLIC_ROUTE_PREFIXES = ['/auth/', '/careers/', '/fps-match/'];
const PUBLIC_EXACT_ROUTES = new Set([
  '/welcome',
  '/pricing',
  '/auth',
  '/about',
  '/about-us',
  '/talent-network',
  '/contact',
  '/careers',
  '/career',
  '/track-application',
  '/fps-match',
]);

const ADMIN_ONLY_ROUTE_PREFIXES = [
  '/job-platform-admin',
  '/admin',
  '/admin-console',
  '/executive-dashboard',
  '/team-management',
  '/policy-console',
  '/admin-system',
  '/admin-activity-log',
  '/email-templates-admin',
  '/performance-observability',
  '/route-health-report',
  '/safe-deployment',
  '/ops-performance',
  '/ops-route-health',
  '/ai-feature-dashboard',
  '/i18n-drift-dashboard',
];

const FREE_LIMITED_UI_PREFIXES = [
  '/content-studio',
  '/workspace',
  '/features/content-studio',
  '/features/analytics-reports',
  '/mini-apps/ai-accounting',
  '/mini-apps/creator-exchange',
  '/subscription/mobile-money',
  '/job-platform-employer',
  '/certificate-operations',
  '/admin/email-delivery-ledger',
  '/job-platform-admin',
];

// POLICY 2026-06.v3: no Basic-gated canonical feature routes remain.
const BASIC_AUTHENTICATED_UI_PREFIXES: string[] = [];


function normalizePlanForSession(planRaw: string): 'free' | 'basic' | 'premium' {
  const plan = String(planRaw || 'free').toLowerCase();
  if (plan === 'premium') return 'premium';
  if (plan === 'basic') return 'basic';
  return 'free';
}

function isRouteInPrefix(path: string, prefix: string) {
  if (path === prefix) return true;
  return path.startsWith(`${prefix}/`);
}

function isAdminOnlyRoute(path: string) {
  return ADMIN_ONLY_ROUTE_PREFIXES.some((prefix) => isRouteInPrefix(path, prefix));
}


function isPublicRoute(path: string) {
  if (PUBLIC_EXACT_ROUTES.has(path)) return true;
  return PUBLIC_ROUTE_PREFIXES.some((prefix) => path.startsWith(prefix));
}

export function AccessControlProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const [session, setSession] = useState<AccessSession | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated || !user) {
      setSession(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await api.get('/access-control/session', {
        timeout: 4000,
        silentLoading: true,
      });
      setSession(res.data || null);
    } catch {
      const employeePermissions = Array.isArray((user as any)?.employee_permissions)
        ? (user as any).employee_permissions.map((perm: any) => String(perm))
        : [];
      // Security-first fallback: never elevate to admin when entitlement fetch fails.
      const actorType: 'user' | 'employee' | 'admin' = employeePermissions.length > 0 ? 'employee' : 'user';
      const fallbackPlan = normalizePlanForSession(String((user as any)?.payment_verified ? (user as any)?.subscription_plan : 'free'));

      setSession({
        effective_plan: fallbackPlan,
        subscription_access_profile: fallbackPlan === 'free'
          ? 'limited'
          : fallbackPlan === 'basic'
            ? 'almost_unlimited'
            : 'full_unlimited',
        entitlement_engine: 'ai_driven_entitlements_v2',
        actor_type: actorType,
        is_admin: false,
        platform_role: (user as any)?.platform_role || null,
        employee_permissions: employeePermissions,
        feature_entitlements: {},
        ui_route_policies: [],
      });
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasPermission = useCallback((permission: string) => {
    if (!permission) return false;
    if (hasAdminConsoleVisibility(user as any) || session?.is_admin) return true;
    const permissions = new Set((session?.employee_permissions || user?.employee_permissions || []).map((p) => String(p)));
    return permissions.has(permission);
  }, [session?.employee_permissions, session?.is_admin, user]);

  const effectivePlan = useMemo<'free' | 'basic' | 'premium'>(() => {
    if (session?.effective_plan) {
      return normalizePlanForSession(String(session.effective_plan));
    }
    if (hasAdminConsoleVisibility(user as any) || session?.is_admin) return 'premium';
    return normalizePlanForSession(String((user as any)?.payment_verified ? (user as any)?.subscription_plan : 'free'));
  }, [session?.effective_plan, session?.is_admin, user]);

  const canAccessPlan = useCallback((requiredPlan: 'basic' | 'premium') => {
    if (hasAdminConsoleVisibility(user as any) || session?.is_admin) return true;
    const requiredLevel = PLAN_LEVEL[requiredPlan] ?? 1;
    const currentLevel = PLAN_LEVEL[effectivePlan] ?? 0;
    return currentLevel >= requiredLevel;
  }, [effectivePlan, session?.is_admin, user]);

  const canAccessRoute = useCallback((path: string): AccessDecision => {
    if (!path) return { allowed: true };

    const normalizedPath = (
      normalizeIncomingSystemPath(String(path || '').split(/[?#]/)[0] || '/')
        .replace(/\/+$/, '')
    ) || '/';

    if (!isAuthenticated) {
      if (isPublicRoute(normalizedPath)) return { allowed: true };
      return {
        allowed: false,
        reason: 'unauthenticated',
        message: 'Sign in is required for this route.',
        redirectTo: '/welcome',
      };
    }

    // ── SUBSCRIPTION ACCESS CONTROL ──
    // Free  → Limited access (FREE_TIER_FEATURE_PREFIXES only)
    // Basic → Almost unlimited (all /features/* except PREMIUM routes)
    // Premium → Full unlimited access (everything)
    // Auto-enforced at platform global level — no exceptions (except admin).

    const effectivePlan = session?.effective_plan || user?.subscription_plan || 'free';
    const accessProfile = String(
      session?.subscription_access_profile
      || (effectivePlan === 'free' ? 'limited' : effectivePlan === 'basic' ? 'almost_unlimited' : 'full_unlimited')
    );
    const level = PLAN_LEVEL[effectivePlan] ?? 0;

    // Unified tier routing: backend session is the source of truth; static lists are offline fallback.
    const tierRoutes = session?.ui_tier_routes || {};
    const freeFeaturePrefixes = tierRoutes.free_feature_prefixes?.length ? tierRoutes.free_feature_prefixes : FREE_TIER_FEATURE_PREFIXES;
    const basicUiPrefixes = tierRoutes.basic_ui_prefixes?.length ? tierRoutes.basic_ui_prefixes : BASIC_UI_PREFIXES;
    const premiumUiPrefixes = tierRoutes.premium_ui_prefixes?.length ? tierRoutes.premium_ui_prefixes : PREMIUM_UI_PREFIXES;
    const basicAuthPrefixes = tierRoutes.basic_authenticated_ui_prefixes?.length ? tierRoutes.basic_authenticated_ui_prefixes : BASIC_AUTHENTICATED_UI_PREFIXES;
    const freeLimitedPrefixes = tierRoutes.free_limited_ui_prefixes?.length ? tierRoutes.free_limited_ui_prefixes : FREE_LIMITED_UI_PREFIXES;

    // /features hub page (navigation/menu) — accessible to all authenticated users
    if (normalizedPath === '/features') {
      return { allowed: true };
    }

    // Admin users have full platform access for management purposes
    if (hasAdminConsoleVisibility(user as any) || session?.is_admin) {
      return { allowed: true };
    }

    if (isAdminOnlyRoute(normalizedPath)) {
      const redirectTo = normalizedPath.startsWith('/job-platform-admin')
        ? '/job-platform-candidate'
        : '/dashboard';
      return {
        allowed: false,
        reason: 'admin_required',
        message: 'Administrator access is required for this route.',
        redirectTo,
      };
    }

    const policy = (session?.ui_route_policies || []).find((p) => normalizedPath.startsWith(p.prefix));
    if (policy && !hasPermission(policy.permission)) {
      return {
        allowed: false,
        reason: 'permission_required',
        message: 'You do not have the required platform permission for this route.',
        redirectTo: '/dashboard',
      };
    }

    // Premium-only features: require Premium plan
    if (premiumUiPrefixes.some((prefix) => normalizedPath.startsWith(prefix)) && level < 2) {
      return {
        allowed: false,
        reason: 'premium_required',
        message: 'This feature requires a Premium subscription.',
        redirectTo: '/subscription/plans',
      };
    }

    if (basicAuthPrefixes.some((prefix) => normalizedPath.startsWith(prefix)) && level < 1) {
      return {
        allowed: false,
        reason: 'basic_required',
        message: 'This feature requires a Basic or Premium subscription.',
        redirectTo: '/subscription/plans',
      };
    }

    // Free tier: limited access — only FREE_TIER_FEATURE_PREFIXES allowed
    // All other /features/* routes require Basic or higher
    if (basicUiPrefixes.some((prefix) => normalizedPath.startsWith(prefix)) && level < 1) {
      // Check if this specific feature is in the free tier allowlist
      const isFreeFeature = freeFeaturePrefixes.some((fp) => normalizedPath.startsWith(fp));
      if (isFreeFeature) {
        return { allowed: true };
      }
      return {
        allowed: false,
        reason: 'basic_required',
        message: 'This feature requires a Basic or Premium subscription.',
        redirectTo: '/subscription/plans',
      };
    }

    // Free plan: additional high-value routes blocked
    if (accessProfile === 'limited' && freeLimitedPrefixes.some((prefix) => normalizedPath.startsWith(prefix))) {
      return {
        allowed: false,
        reason: 'free_limited_access',
        message: 'This feature is available on Basic or Premium plans.',
        redirectTo: '/subscription/plans',
      };
    }

    return { allowed: true };
  }, [hasPermission, isAuthenticated, session, user]);

  const value = useMemo<AccessControlContextType>(() => ({
    loading,
    session,
    effectivePlan,
    hasPermission,
    canAccessRoute,
    canAccessPlan,
    refresh,
  }), [loading, session, effectivePlan, hasPermission, canAccessRoute, canAccessPlan, refresh]);

  return <AccessControlContext.Provider value={value}>{children}</AccessControlContext.Provider>;
}

export function useAccessControl() {
  const context = useContext(AccessControlContext);
  if (!context) {
    return {
      loading: false,
      session: null,
      effectivePlan: 'free',
      hasPermission: () => false,
      canAccessRoute: () => ({ allowed: true }),
      canAccessPlan: () => false,
      refresh: async () => {},
    } as AccessControlContextType;
  }
  return context;
}
