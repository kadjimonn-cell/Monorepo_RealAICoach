export const KNOWN_TOP_LEVEL_SEGMENTS = new Set([
  '',
  '(tabs)',
  'about',
  'about-us',
  'ai-problem-solver',
  'achievements',
  'admin',
  'admin-activity-log',
  'admin-console',
  'admin-system',
  'ai-briefing',
  'ai-feature-dashboard',
  'ai-learning-hub',
  'ai-learning-hub-kpi',
  'ai-coaching-team',
  'auth',
  'blog',
  'book',
  'book-meeting',
  'calendar',
  'career',
  'careers',
  'certificate-compare',
  'certificate-gallery',
  'certificate-operations',
  'certificate-verify',
  'chat',
  'contact',
  'content-library',
  'cookies',
  'currency-selector',
  'dashboard',
  'downloads',
  'edit-profile',
  'email-templates-admin',
  'employer-apply',
  'employer-console',
  'executive-dashboard',
  'faq',
  'feature-gallery',
  'features',
  'feedback',
  'fps-match',
  'gdpr',
  'help',
  'hiring-hub',
  'home',
  'i18n-drift-dashboard',
  'id-verification',
  'id-checker',
  'id-verify-mobile',
  'integrations',
  'invite-accept',
  'interview-room',
  'job-platform',
  'job-platform-admin',
  'job-platform-candidate',
  'job-platform-employer',
  'job-search',
  'nova-curation-hub',
  'language-selector',
  'learner-portfolio',
  'leaderboard',
  'login',
  'logout',
  'messages',
  'mini-apps',
  'my-analytics',
  'my-tickets',
  'notifications',
  'onboarding',
  'ops-performance',
  'ops-route-health',
  'payment-document-v2',
  'payment-history',
  'payment-history-export-v2',
  'payment-result',
  'performance-observability',
  'policy-console',
  'practice',
  'press',
  'pricing',
  'privacy-policy',
  'privacy-request',
  'privacy-verify',
  'privacy-security',
  'profile',
  'progress',
  'progress-tracker',
  'referrals',
  'route-health-report',
  'safe-deployment',
  'scan-history',
  'scenario',
  'security',
  'session-history',
  'settings',
  'shared',
  'shared-calendar',
  'subscription',
  'system-status',
  'talent-network',
  'talent-network-admin',
  'team-management',
  'terms',
  'track-application',
  'verify',
  'welcome',
]);

export function getFirstRouteSegment(pathname: string) {
  return pathname.split(/[?#]/)[0].split('/').filter(Boolean)[0] || '';
}

export function hasKnownTopLevelSegment(pathname: string) {
  const normalized = normalizeIncomingSystemPath(pathname || '/');
  return KNOWN_TOP_LEVEL_SEGMENTS.has(getFirstRouteSegment(normalized));
}

export function normalizeIncomingSystemPath(path: string) {
  if (!path) return '/';

  let normalized = path.trim();

  try {
    const parsed = new URL(normalized, 'realaicoach://app.home');
    const host = (parsed.hostname || '').toLowerCase();
    const pathname = parsed.pathname || '/';

    if (host.includes('app.emergent.sh') || host.includes('emergent.sh')) {
      return '/';
    }

    normalized = `${pathname}${parsed.search || ''}${parsed.hash || ''}`;
  } catch {
    normalized = normalized.replace(/^[a-z]+:\/\/[^/]+/i, '');
  }

  normalized = normalized.replace(/^\/--(?=\/)/, '');
  if (!normalized.startsWith('/')) {
    normalized = `/${normalized}`;
  }

  return normalized.replace(/\/+/g, '/');
}