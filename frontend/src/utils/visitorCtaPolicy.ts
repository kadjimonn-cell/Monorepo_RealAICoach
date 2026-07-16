import { normalizeIncomingSystemPath } from './routeResolution';

type Surface = 'welcome' | 'footer' | 'public';

type ResolveOptions = {
  isAuthenticated: boolean;
  surface: Surface;
  fallbackPath?: string;
};

const VISITOR_ALLOWED_PREFIXES = [
  '/welcome',
  '/pricing',
  '/about',
  '/about-us',
  '/careers',
  '/career',
  '/press',
  '/blog',
  '/contact',
  '/talent-network',
  '/privacy-policy',
  '/privacy-request',
  '/terms',
  '/security',
  '/gdpr',
  '/cookies',
  '/track-application',
];

const VISITOR_ALLOWED_AUTH_EXACT = new Set([
  '/auth/login',
  '/auth/register',
]);

const VISITOR_BLOCKED_PREFIXES = [
  '/auth',
  '/subscription',
  '/dashboard',
  '/(tabs)',
  '/features',
  '/settings',
  '/profile',
  '/messages',
  '/notifications',
  '/admin',
  '/job-platform',
  '/my-analytics',
  '/content-library',
  '/ai-briefing',
  '/leaderboard',
];

function matchesPrefix(path: string, prefix: string): boolean {
  return (
    path === prefix
    || path.startsWith(`${prefix}/`)
    || path.startsWith(`${prefix}?`)
    || path.startsWith(`${prefix}#`)
  );
}

function stripPathDecorators(path: string): string {
  return (path.split(/[?#]/)[0] || '/').replace(/\/+$/, '') || '/';
}

export function resolveVisitorCtaPath(targetPath: string, options: ResolveOptions): string {
  const fallback = String(options.fallbackPath || '/welcome').trim() || '/welcome';
  const normalizedTarget = normalizeIncomingSystemPath(String(targetPath || '').trim() || fallback);
  const normalizedTargetPathOnly = stripPathDecorators(normalizedTarget);

  if (options.isAuthenticated) {
    return normalizedTarget;
  }

  if (VISITOR_ALLOWED_AUTH_EXACT.has(normalizedTargetPathOnly)) {
    return normalizedTarget;
  }

  if (VISITOR_ALLOWED_PREFIXES.some((prefix) => matchesPrefix(normalizedTarget, prefix))) {
    return normalizedTarget;
  }

  if (VISITOR_BLOCKED_PREFIXES.some((prefix) => matchesPrefix(normalizedTarget, prefix))) {
    return fallback;
  }

  if (options.surface === 'welcome' || options.surface === 'footer') {
    return fallback;
  }

  return '/welcome';
}

export function buildWelcomePricingSurfaceTarget(source: string = 'pricing-compare'): string {
  const params = new URLSearchParams();
  params.set('section', 'pricing');
  if (source && String(source).trim()) {
    params.set('source', String(source).trim());
  }
  return `/welcome?${params.toString()}`;
}
