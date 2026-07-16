import { resolveVisitorCtaPath } from '../utils/visitorCtaPolicy';
import { buildAnalyticsSource } from '../utils/buildAnalyticsSource';

type ResolveMiniAppRedirectOptions = {
  isAuthenticated?: boolean;
};

const JOB_PLATFORM_MINI_APP_ROUTE = '/mini-apps/job-platform';
const MOBILE_MONEY_MINI_APP_ROUTE = '/mini-apps/mobile-money';

function buildMiniAppVisitorRegisterFallback(pathname: string): string {
  const normalized = String(pathname || '/mini-apps').trim() || '/mini-apps';
  const routeSlug = normalized
    .replace(/^\/+/, '')
    .replace(/\/+$/g, '')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .toLowerCase() || 'mini-apps';
  const params = new URLSearchParams();
  params.set('source', buildAnalyticsSource(routeSlug === 'mini-apps' ? 'feature-entry' : routeSlug.replace(/^mini-apps/, 'feature-entry')));
  params.set('return_to', normalized);
  return `/auth/register?${params.toString()}`;
}

export const MINI_APP_REDIRECT_MAP: Record<string, string> = {
  '/mini-apps': '/features',
  '/mini-apps/onboarding': '/onboarding',
  [JOB_PLATFORM_MINI_APP_ROUTE]: '/job-platform',
  [MOBILE_MONEY_MINI_APP_ROUTE]: '/subscription/plans',
  '/mini-apps/marketplace': '/features/smartbuy',
  '/mini-apps/digital-bank': '/features/pennypilot',
  '/mini-apps/creator-exchange': '/my-analytics',
  '/mini-apps/ai-accounting': '/features/pennypilot',
  '/mini-apps/invoice-generator': '/content-library',
  '/mini-apps/drama-box': '/content-library',
  '/mini-apps/music-streaming': '/features/ai-speech',
  '/mini-apps/local-music': '/features/ai-speech',
};

export function resolveMiniAppRedirect(pathname: string, options: ResolveMiniAppRedirectOptions = {}): string | null {
  if (!pathname.startsWith('/mini-apps')) return null;

  const normalized = pathname.replace(/\/+/g, '/').replace(/\/$/, '') || '/mini-apps';
  const fallbackPath = buildMiniAppVisitorRegisterFallback(normalized);

  let target = MINI_APP_REDIRECT_MAP[normalized] || '/features';

  if (normalized === JOB_PLATFORM_MINI_APP_ROUTE || normalized.startsWith(`${JOB_PLATFORM_MINI_APP_ROUTE}/`)) {
    target = '/job-platform';
  }

  return resolveVisitorCtaPath(target, {
    isAuthenticated: Boolean(options.isAuthenticated),
    surface: 'public',
    fallbackPath,
  });
}
