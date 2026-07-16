import { getRouteE2EEvidenceTag } from './platformRouteEvidenceTags';

export type PlatformRoutePhase = 'B' | 'EXEMPT';

export interface PlatformRouteStatus {
  phase: PlatformRoutePhase;
  clusterId: string;
  clusterLabel: string;
  matchedPrefix: string;
  recommendedLiveRoute: string;
  blockContent: boolean;
  evidenceTag?: string;
  evidenceRefs?: string[];
}

interface PlatformRouteRule {
  phase: 'B';
  clusterId: string;
  clusterLabel: string;
  prefixes: string[];
  recommendedLiveRoute: string;
  blockContent?: boolean;
}

const EXEMPT_PREFIXES = [
  '/auth', '/login', '/logout', '/register',
  '/about', '/about-us', '/pricing', '/contact', '/press', '/blog',
  '/cookies', '/terms', '/privacy-policy', '/privacy-security', '/privacy-request', '/privacy-verify', '/gdpr', '/verify',
  '/shared', '/shared-calendar', '/book/',
  '/careers/portal/', '/careers/schedule/', '/careers/interview/', '/careers/offer/', '/careers/video-qa/', '/careers/track/',
  '/subscription/payment', '/subscription/success', '/subscription/payment-result', '/payment-result',
];

const PLATFORM_ROUTE_RULES: PlatformRouteRule[] = [
  // Phase B — globally promoted live clusters.
  {
    phase: 'B',
    clusterId: 'verified-hiring',
    clusterLabel: 'Verified Hiring + Identity Cluster',
    prefixes: ['/job-platform', '/hiring-hub', '/career', '/careers', '/track-application', '/id-checker', '/id-verification', '/id-verify-mobile'],
    recommendedLiveRoute: '/job-platform',
  },
  {
    phase: 'B',
    clusterId: 'verified-admin-consoles',
    clusterLabel: 'Verified Executive + Operations Consoles',
    prefixes: ['/executive-dashboard', '/admin-console'],
    recommendedLiveRoute: '/executive-dashboard?section=jobs',
  },

  // Global promotion: move former Phase-C/demo clusters to Phase-B.
  {
    phase: 'B',
    clusterId: 'feature-demo-cluster',
    clusterLabel: 'Feature Discovery + Demo Surfaces',
    prefixes: ['/feature-gallery', '/features', '/mini-apps', '/ai-feature-dashboard'],
    recommendedLiveRoute: '/job-platform',
  },

  // Global promotion: move former Phase-C live-wired clusters to Phase-B.
  {
    phase: 'B',
    clusterId: 'core-learning-cluster',
    clusterLabel: 'AI Learning + Problem Solving',
    prefixes: ['/ai-learning-hub', '/ai-coaching-team', '/ai-briefing'],
    recommendedLiveRoute: '/job-platform',
  },
  {
    phase: 'B',
    clusterId: 'insights-cluster',
    clusterLabel: 'Analytics + Insights',
    prefixes: ['/my-analytics', '/leaderboard', '/progress', '/notifications', '/certificate-gallery', '/certificate-operations'],
    recommendedLiveRoute: '/job-platform',
  },
  {
    phase: 'B',
    clusterId: 'account-support-cluster',
    clusterLabel: 'Account + Support + Productivity',
    prefixes: ['/dashboard', '/home', '/settings', '/profile', '/help', '/my-tickets', '/integrations', '/book-meeting', '/calendar', '/content-library', '/referrals', '/payment-history', '/subscription/plans', '/subscription/mobile'],
    recommendedLiveRoute: '/job-platform',
  },
];

const normalizePath = (routePath: string): string => {
  const route = String(routePath || '').trim();
  if (!route) return '/';
  if (route.startsWith('/')) return route;
  return `/${route}`;
};

const isExemptRoute = (routePath: string): boolean => {
  const path = normalizePath(routePath).toLowerCase();
  return EXEMPT_PREFIXES.some((prefix) => path === prefix || path.startsWith(prefix));
};

export const getPlatformRouteStatus = (routePath: string): PlatformRouteStatus => {
  const path = normalizePath(routePath);
  const lowerPath = path.toLowerCase();

  if (isExemptRoute(lowerPath)) {
    return {
      phase: 'EXEMPT',
      clusterId: 'public-or-auth',
      clusterLabel: 'Public/Auth Surface',
      matchedPrefix: lowerPath,
      recommendedLiveRoute: '/job-platform',
      blockContent: false,
    };
  }

  const evidenceTag = getRouteE2EEvidenceTag(lowerPath);
  if (evidenceTag && evidenceTag.promotedPhase === 'B') {
    return {
      phase: 'B',
      clusterId: 'wave3-verified-live-routes',
      clusterLabel: `Wave 3 Verified Routes · ${evidenceTag.routeName}`,
      matchedPrefix: evidenceTag.routePrefix,
      recommendedLiveRoute: '/job-platform',
      blockContent: false,
      evidenceTag: evidenceTag.evidenceTag,
      evidenceRefs: evidenceTag.reportRefs,
    };
  }

  for (const rule of PLATFORM_ROUTE_RULES) {
    const matchedPrefix = rule.prefixes.find((prefix) => lowerPath === prefix || lowerPath.startsWith(prefix));
    if (!matchedPrefix) continue;
    return {
      phase: rule.phase,
      clusterId: rule.clusterId,
      clusterLabel: rule.clusterLabel,
      matchedPrefix,
      recommendedLiveRoute: rule.recommendedLiveRoute,
      blockContent: Boolean(rule.blockContent),
    };
  }

  // Unknown authenticated route defaults to Phase B after global promotion.
  return {
    phase: 'B',
    clusterId: 'unclassified-auth-route',
    clusterLabel: 'Unclassified Authenticated Route (Global B Default)',
    matchedPrefix: lowerPath,
    recommendedLiveRoute: '/job-platform',
    blockContent: false,
  };
};
