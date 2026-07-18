import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { secureGetToken, secureClearToken } from '../utils/secureTokenStore';
import { beginGlobalLoading, endGlobalLoading } from './loadingOrchestrator';
import { recordShellHealthMetric } from './shellHealthMonitor';
import { emitFeatureQuotaLimit } from './featureQuotaEvents';
import { getBackendOriginConsistency, resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { buildObservabilityHeaders } from './traceContext';
import { initializeBrowserObservability } from './otelClient';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const API_URL = resolveRuntimeBaseUrl();
const BACKEND_ORIGIN_CONSISTENCY = getBackendOriginConsistency();

const BASE_URL = API_URL ? `${API_URL}/api` : '/api';

initializeBrowserObservability();

// In-memory token cache to avoid AsyncStorage reads on every request
let cachedToken: string | null = null;
const WEB_COOKIE_ONLY_AUTH = true;

export const setCachedToken = (token: string | null) => {
  cachedToken = token;
};

function readBrowserTokenFallback(): string | null {
  if (WEB_COOKIE_ONLY_AUTH && typeof window !== 'undefined') return null;
  if (typeof window === 'undefined') return null;
  try {
    const candidates = [
      window.localStorage.getItem('session_token'),
      window.localStorage.getItem('token'),
      window.localStorage.getItem('access_token'),
      window.sessionStorage.getItem('session_token'),
      window.sessionStorage.getItem('token'),
      window.sessionStorage.getItem('access_token'),
    ];
    const found = candidates.find((value) => Boolean(value && value.trim()));
    return found ? String(found).trim() : null;
  } catch {
    return null;
  }
}

function readCookieValue(name: string): string | null {
  if (typeof document === 'undefined') return null;
  try {
    const pairs = String(document.cookie || '').split(';');
    for (const pair of pairs) {
      const trimmed = pair.trim();
      if (!trimmed) continue;
      const [k, ...rest] = trimmed.split('=');
      if (k === name) {
        return decodeURIComponent(rest.join('='));
      }
    }
  } catch {
    return null;
  }
  return null;
}

// ── Token retrieval ─────────────────────────────────────────────────────
async function getAuthToken(): Promise<string | null> {
  if (WEB_COOKIE_ONLY_AUTH && typeof window !== 'undefined') {
    cachedToken = null;
    return null;
  }

  const browserToken = readBrowserTokenFallback();
  if (browserToken && browserToken !== cachedToken) {
    cachedToken = browserToken;
    return browserToken;
  }
  if (!browserToken && cachedToken) {
    cachedToken = null;
  }

  if (cachedToken) return cachedToken;

  if (Platform.OS !== 'web') {
    try {
      const secure = await secureGetToken();
      if (secure) { cachedToken = secure; return secure; }
    } catch { /* fall through */ }
  }

  try {
    const token = await AsyncStorage.getItem('session_token');
    if (token) { cachedToken = token; return token; }
  } catch { /* fall through */ }

  try {
    const token = await AsyncStorage.getItem('token');
    if (token) { cachedToken = token; return token; }
  } catch { /* fall through */ }

  try {
    const token = await AsyncStorage.getItem('access_token');
    if (token) { cachedToken = token; return token; }
  } catch { /* fall through */ }

  const fallbackBrowserToken = readBrowserTokenFallback();
  if (fallbackBrowserToken) { cachedToken = fallbackBrowserToken; return fallbackBrowserToken; }
  return null;
}

export async function ensureAuthTokenLoaded(): Promise<string | null> {
  return getAuthToken();
}

// ── Error class matching axios error shape ──────────────────────────────
class ApiError extends Error {
  response?: { data: any; status: number; headers: Headers };
  config?: any;
  authUnauthorized?: boolean;
  authErrorCode?: string;
  authEndpoint?: string;
  subscriptionRequired?: boolean;
  requiredPlan?: string;
  currentPlan?: string;
  upgradeUrl?: string;
  subscriptionMessage?: string;
  policyGateBlocked?: boolean;
  policyGateReason?: string;
  policyGateFailedChecks?: string[];
  policyGateDecisionId?: string;

  constructor(message: string, response?: { data: any; status: number; headers: Headers }, config?: any) {
    super(message);
    this.name = 'ApiError';
    this.response = response;
    this.config = config;
  }
}

function extractPolicyGatePayload(payload: any): any | null {
  if (!payload) return null;
  if (payload.code === 'PRODUCTION_POLICY_GATE_BLOCKED') return payload;
  if (payload.detail?.code === 'PRODUCTION_POLICY_GATE_BLOCKED') return payload.detail;
  return null;
}

function extractPlatformControlPayload(payload: any): any | null {
  if (!payload) return null;
  if (typeof payload?.code === 'string' && payload.code.startsWith('PLATFORM_')) return payload;
  if (typeof payload?.detail?.code === 'string' && payload.detail.code.startsWith('PLATFORM_')) return payload.detail;
  return null;
}

function extractStructuredErrorCode(payload: any): string {
  const candidates = [
    payload?.error_code,
    payload?.code,
    payload?.detail?.error_code,
    payload?.detail?.code,
    payload?.error?.error_code,
    payload?.error?.code,
    payload?.detail?.error?.error_code,
    payload?.detail?.error?.code,
  ];
  const resolved = candidates.find((value) => typeof value === 'string' && String(value).trim().length > 0);
  return String(resolved || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
}

function shouldResetTokenOn401(fullUrl: string, payload: any): boolean {
  const endpoint = normalizeNetworkIssueUrl(fullUrl);
  const errorCode = extractStructuredErrorCode(payload);

  const authSensitivePaths = [
    '/auth/me',
    '/auth/profile',
    '/auth/session',
    '/users/me',
    '/session/validate',
  ];

  const isAuthSensitiveEndpoint = authSensitivePaths.some((path) => endpoint.includes(path));

  const authFamilyPrefixes = [
    '/api/auth/',
    '/auth/',
    '/api/session/',
    '/session/',
    '/users/me',
  ];
  const isAuthFamilyEndpoint = authFamilyPrefixes.some((path) => endpoint.includes(path));
  if (!isAuthFamilyEndpoint) {
    return false;
  }

  const invalidTokenCodes = [
    'unauthorized',
    'not_authenticated',
    'auth_unauthorized',
    'invalid_session',
    'session_expired',
    'token_expired',
    'jwt_invalid',
    'auth_session_invalid',
    'invalid_token',
    'session_token_missing',
    'invalid_or_expired_session',
  ];
  const hasInvalidCode = Boolean(errorCode) && invalidTokenCodes.some((signal) => errorCode === signal || errorCode.endsWith(`.${signal}`));

  if (isAuthSensitiveEndpoint) {
    // Avoid aggressive token wipe for transient/race 401s on auth bootstrap calls.
    // Only clear when backend emits explicit structured invalid-session code.
    return hasInvalidCode;
  }

  return hasInvalidCode;
}

// ── Core request function ───────────────────────────────────────────────
const MAX_RETRIES = 3;
const RETRY_DELAY_BASE = 1000;
const DEFAULT_MUTATION_TIMEOUT = 120000;
const DEFAULT_GET_TIMEOUT = 20000;
const DEFAULT_BINARY_GET_TIMEOUT = 30000;

interface RequestConfig {
  params?: Record<string, any>;
  headers?: Record<string, string>;
  responseType?: 'json' | 'blob' | 'text';
  timeout?: number;
  silentLoading?: boolean;
  forceSubscriptionUpgradePrompt?: boolean;
  skipDedupe?: boolean;
  allowAdminSubscriptionPlansEndpoint?: boolean;
  onUploadProgress?: (event: { loaded: number; total: number }) => void;
  _retryCount?: number;
}

const SUBSCRIPTION_UPGRADE_SUPPRESSED_PREFIXES = [
  '/api/tos/',
  '/api/platform-control/public/',
  '/api/system/health',
  '/api/health',
  '/api/subscription-prompt/telemetry',
  '/api/subscription-conversion/telemetry',
];

function shouldEmitSubscriptionUpgradePrompt(config: RequestConfig, fullUrl: string, method: string): boolean {
  const normalized = normalizeNetworkIssueUrl(fullUrl);
  const upperMethod = String(method || 'GET').toUpperCase();

  if (SUBSCRIPTION_UPGRADE_SUPPRESSED_PREFIXES.some((prefix) => normalized.startsWith(prefix))) {
    return false;
  }

  // Background/polling reads should never trigger disruptive upgrade modal overlays.
  if (Boolean(config?.silentLoading) && upperMethod === 'GET') {
    return false;
  }

  // Policy: auto API-triggered upgrade prompt should appear only on home-like routes unless forced.
  if (typeof window !== 'undefined' && !config?.forceSubscriptionUpgradePrompt) {
    const path = String(window.location?.pathname || '/');
    const isHomeLike = path === '/' || path === '/welcome' || path === '/home' || path === '/dashboard';
    if (!isHomeLike) {
      return false;
    }
  }

  return true;
}

const inFlightGetRequests = new Map<string, Promise<{ data: any; status: number; headers: Headers }>>();
const lowPriorityCache = new Map<string, { data: any; status: number; headers: Headers; expiresAt: number }>();
const rateLimitedUntil = new Map<string, number>();
const forbiddenCooldownUntil = new Map<string, number>();
const noisyEndpointCooldownUntil = new Map<string, number>();

const OPTIONAL_FORBIDDEN_COOLDOWN_RULES: { match: string; methods: string[]; cooldownMs: number }[] = [
  { match: '/geo/detect', methods: ['GET'], cooldownMs: 10 * 60 * 1000 },
  { match: '/subscription-conversion/telemetry', methods: ['POST'], cooldownMs: 10 * 60 * 1000 },
  { match: '/subscription-prompt/telemetry', methods: ['POST'], cooldownMs: 10 * 60 * 1000 },
  { match: '/gps/state', methods: ['GET'], cooldownMs: 2 * 60 * 1000 },
  { match: '/gps/consistency/check', methods: ['POST'], cooldownMs: 2 * 60 * 1000 },
  { match: '/subscriptions/renewal-banner', methods: ['GET'], cooldownMs: 2 * 60 * 1000 },
  { match: '/subscriptions/plans', methods: ['GET'], cooldownMs: 2 * 60 * 1000 },
  { match: '/onboarding-ab/assign', methods: ['POST'], cooldownMs: 2 * 60 * 1000 },
  { match: '/onboarding-ab/convert', methods: ['POST'], cooldownMs: 2 * 60 * 1000 },
];

function getOptionalForbiddenCooldown(fullUrl: string, method: string): { key: string; cooldownMs: number } | null {
  const normalized = normalizeNetworkIssueUrl(fullUrl);
  const upperMethod = String(method || 'GET').toUpperCase();
  const rule = OPTIONAL_FORBIDDEN_COOLDOWN_RULES.find((candidate) => (
    normalized.startsWith(`/api${candidate.match}`) && candidate.methods.includes(upperMethod)
  ));
  if (!rule) return null;
  return {
    key: `${upperMethod}::${normalized}`,
    cooldownMs: rule.cooldownMs,
  };
}

const LOW_PRIORITY_CACHE_RULES: { match: string; ttlMs: number }[] = [
  { match: '/prompt-experiment/variant', ttlMs: 5 * 60 * 1000 },
  { match: '/config/global', ttlMs: 5 * 60 * 1000 },
  { match: '/features/registry', ttlMs: 2 * 60 * 1000 },
  { match: '/home/dashboard-stats', ttlMs: 30 * 1000 },
  { match: '/home/chart-data', ttlMs: 45 * 1000 },
  { match: '/home/activity-feed', ttlMs: 45 * 1000 },
  { match: '/home/checklist-status', ttlMs: 60 * 1000 },
  { match: '/home/badges', ttlMs: 60 * 1000 },
  { match: '/home/tour-status', ttlMs: 5 * 60 * 1000 },
  { match: '/onboarding/progress', ttlMs: 60 * 1000 },
  { match: '/onboarding-wizard/status', ttlMs: 5 * 60 * 1000 },
  { match: '/admin/notifications/live', ttlMs: 20 * 1000 },
  { match: '/admin/live-activity/alerts', ttlMs: 20 * 1000 },
  { match: '/admin/ai-insights/latest/', ttlMs: 60 * 1000 },
  { match: '/admin/ai-autofix/latest', ttlMs: 45 * 1000 },
  { match: '/admin/ai-autofix/config', ttlMs: 60 * 1000 },
  { match: '/admin/performance-guardian/budgets', ttlMs: 60 * 1000 },
  { match: '/payments/currencies', ttlMs: 5 * 60 * 1000 },
  { match: '/system/vanity-metrics', ttlMs: 45 * 1000 },
  { match: '/system/live-metrics', ttlMs: 3 * 1000 },
  { match: '/geo/detect', ttlMs: 15 * 60 * 1000 },
  { match: '/i18n/language-guidance', ttlMs: 15 * 60 * 1000 },
  { match: '/i18n/user-preference', ttlMs: 2 * 60 * 1000 },
  { match: '/subscriptions/status', ttlMs: 60 * 1000 },
  { match: '/subscriptions/renewal-banner', ttlMs: 2 * 60 * 1000 },
  { match: '/subscriptions/plans', ttlMs: 2 * 60 * 1000 },
  { match: '/notifications/', ttlMs: 15 * 1000 },
  { match: '/gps/state', ttlMs: 15 * 1000 },
  { match: '/changelog/latest', ttlMs: 2 * 60 * 1000 },
];

const FRESHNESS_CRITICAL_ENDPOINT_PATTERNS: string[] = [
  '/admin/platform-health/',
  '/subscriptions/checkout-preview',
  '/subscriptions/mobile-money/gateways',
  '/subscriptions/mobile-money/fedapay-policy',
  '/subscriptions/gateway-config',
  '/subscriptions/mobile-money/sandbox-info',
  '/admin/platform-health/fedapay-webhook-integrity',
];

const NETWORK_ISSUE_EVENT_THROTTLE_MS = 6000;
const NETWORK_ISSUE_EVENT_WINDOW_MS = 45000;
const networkIssueThrottleMap = new Map<string, number>();

const HARD_429_COOLDOWN_RULES: { match: string; methods: string[]; cooldownMs: number }[] = [
  { match: '/gps/state', methods: ['GET'], cooldownMs: 5 * 60 * 1000 },
  { match: '/onboarding-ab/assign', methods: ['POST'], cooldownMs: 5 * 60 * 1000 },
  { match: '/subscriptions/renewal-banner', methods: ['GET'], cooldownMs: 5 * 60 * 1000 },
  { match: '/subscriptions/plans', methods: ['GET'], cooldownMs: 5 * 60 * 1000 },
  { match: '/notifications/', methods: ['GET'], cooldownMs: 3 * 60 * 1000 },
];

const PREEMPTIVE_NOISY_ENDPOINT_COOLDOWN_RULES: { match: string; methods: string[]; cooldownMs: number }[] = [
  { match: '/gps/state', methods: ['GET'], cooldownMs: 20_000 },
  { match: '/onboarding-ab/assign', methods: ['POST'], cooldownMs: 5 * 60 * 1000 },
  { match: '/subscriptions/renewal-banner', methods: ['GET'], cooldownMs: 2 * 60 * 1000 },
  { match: '/subscriptions/plans', methods: ['GET'], cooldownMs: 2 * 60 * 1000 },
  { match: '/notifications/', methods: ['GET'], cooldownMs: 20_000 },
];

function getPreemptiveNoisyEndpointCooldown(fullUrl: string, method: string): number {
  const normalized = normalizeNetworkIssueUrl(fullUrl);
  const upperMethod = String(method || 'GET').toUpperCase();
  const rule = PREEMPTIVE_NOISY_ENDPOINT_COOLDOWN_RULES.find((candidate) => (
    normalized.startsWith(`/api${candidate.match}`) && candidate.methods.includes(upperMethod)
  ));
  return rule?.cooldownMs || 0;
}

function getHard429Cooldown(fullUrl: string, method: string): number {
  const normalized = normalizeNetworkIssueUrl(fullUrl);
  const upperMethod = String(method || 'GET').toUpperCase();
  const rule = HARD_429_COOLDOWN_RULES.find((candidate) => (
    normalized.startsWith(`/api${candidate.match}`) && candidate.methods.includes(upperMethod)
  ));
  return rule?.cooldownMs || 0;
}

function normalizeNetworkIssueUrl(url: string): string {
  if (!url) return 'unknown';
  try {
    const parsed = new URL(url, typeof window !== 'undefined' ? window.location.origin : 'http://localhost');
    return parsed.pathname || url;
  } catch {
    return String(url).split('?')[0] || 'unknown';
  }
}

function emitNetworkIssue(detail: { status?: number; url: string; reason: string }) {
  if (typeof window === 'undefined') return;

  const now = Date.now();
  const endpointKey = normalizeNetworkIssueUrl(detail.url);
  const throttleKey = `${detail.reason}:${endpointKey}:${detail.status || 0}`;
  const previous = networkIssueThrottleMap.get(throttleKey) || 0;

  if (now - previous < NETWORK_ISSUE_EVENT_THROTTLE_MS) {
    return;
  }
  networkIssueThrottleMap.set(throttleKey, now);

  if (networkIssueThrottleMap.size > 400) {
    for (const [key, ts] of networkIssueThrottleMap.entries()) {
      if (now - ts > NETWORK_ISSUE_EVENT_WINDOW_MS) {
        networkIssueThrottleMap.delete(key);
      }
    }
  }

  try {
    window.dispatchEvent(new CustomEvent('app-network-issue', {
      detail: {
        status: Number(detail.status || 0),
        url: endpointKey,
        reason: detail.reason,
        timestamp: now,
      },
    }));
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/services/api.ts#catch1',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

function emitAuthUnauthorized(detail: { url: string; reasonCode: string }) {
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent('app-auth-unauthorized', {
      detail: {
        url: normalizeNetworkIssueUrl(detail.url),
        reasonCode: detail.reasonCode,
        timestamp: Date.now(),
      },
    }));
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/services/api.ts#catch1b',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

function getLowPriorityCacheTtl(fullUrl: string): number {
  const rule = LOW_PRIORITY_CACHE_RULES.find((item) => fullUrl.includes(item.match));
  return rule?.ttlMs || 0;
}

function isFreshnessCriticalEndpoint(fullUrl: string): boolean {
  return FRESHNESS_CRITICAL_ENDPOINT_PATTERNS.some((pattern) => fullUrl.includes(pattern));
}

function getRetryAfterMs(headers: any): number {
  if (!headers) return 0;
  try {
    const value = typeof headers.get === 'function'
      ? headers.get('retry-after')
      : (headers['retry-after'] || headers['Retry-After']);
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed > 0) {
      return parsed * 1000;
    }
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/services/api.ts#catch2',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
  return 0;
}

function isBackgroundProbe(fullUrl: string): boolean {
  const probePatterns = [
    '/api/system/vanity-metrics',
    '/api/gps/state',
    '/api/gps/consistency/check',
    '/api/config/ai-language-guidance',
    '/api/content/metadata',
    '/api/content/recommendations',
    '/api/subscriptions/renewal-banner',
    '/api/subscriptions/plans',
    '/api/notifications/',
    '/api/subscription-conversion/telemetry',
    '/api/onboarding-ab/assign',
    '/api/onboarding-ab/convert',
    '/api/changelog/latest',
    '/api/i18n/user-preference',
  ];
  return probePatterns.some((pattern) => fullUrl.includes(pattern));
}

function rewriteFeature26LegacyReadUrl(method: string, url: string): string {
  const normalizedMethod = String(method || '').toUpperCase();
  if (!['GET', 'HEAD'].includes(normalizedMethod)) {
    return url;
  }

  if (!url || url.startsWith('http')) {
    return url;
  }

  const queryIndex = url.indexOf('?');
  const pathOnly = queryIndex >= 0 ? url.slice(0, queryIndex) : url;
  const queryOnly = queryIndex >= 0 ? url.slice(queryIndex) : '';

  const rules: { pattern: RegExp; replacement: string }[] = [
    { pattern: /^\/jobs\/search$/, replacement: '/hiring/v2/candidate/jobs/search' },
    { pattern: /^\/jobs\/detail\/([^/]+)$/, replacement: '/hiring/v2/candidate/jobs/detail/$1' },
    { pattern: /^\/jobs\/recommendations$/, replacement: '/hiring/v2/candidate/recommendations' },
    { pattern: /^\/jobs\/my-applications$/, replacement: '/hiring/v2/candidate/applications' },
    { pattern: /^\/jobs\/saved$/, replacement: '/hiring/v2/candidate/saved-jobs' },
    { pattern: /^\/jobs\/profile$/, replacement: '/hiring/v2/candidate/profile' },
    { pattern: /^\/jobs\/resume\/score$/, replacement: '/hiring/v2/candidate/resume-score' },
    { pattern: /^\/jobs\/analytics$/, replacement: '/hiring/v2/candidate/analytics' },
    { pattern: /^\/jobs\/portal-summary$/, replacement: '/hiring/v2/dashboard/summary' },
    { pattern: /^\/jobs\/my-posted$/, replacement: '/hiring/v2/employer/jobs' },
    { pattern: /^\/jobs\/applicants\/([^/]+)$/, replacement: '/hiring/v2/employer/applicants/$1' },
    { pattern: /^\/jobs\/employer\/pipeline-board$/, replacement: '/hiring/v2/employer/pipeline-board' },
    { pattern: /^\/jobs\/employer\/pipeline-board\/([^/]+)\/timeline$/, replacement: '/hiring/v2/employer/pipeline-board/$1/timeline' },
    { pattern: /^\/jobs\/employer\/pipeline-board\/([^/]+)\/audit-export\.csv$/, replacement: '/hiring/v2/employer/pipeline-board/$1/audit-export.csv' },
    { pattern: /^\/jobs\/employer\/pipeline-board\/([^/]+)\/audit-export\.pdf$/, replacement: '/hiring/v2/employer/pipeline-board/$1/audit-export.pdf' },
    { pattern: /^\/jobs\/employer\/pipeline-board\/([^/]+)\/audit-download-history$/, replacement: '/hiring/v2/employer/pipeline-board/$1/audit-download-history' },
    { pattern: /^\/jobs\/employer\/offers$/, replacement: '/hiring/v2/employer/offers' },
    { pattern: /^\/jobs\/employer\/sla-alerts$/, replacement: '/hiring/v2/employer/sla-alerts' },
    { pattern: /^\/jobs\/employer\/sla-auto-triggers$/, replacement: '/hiring/v2/employer/sla-auto-triggers' },
    { pattern: /^\/jobs\/employer\/kpi-header$/, replacement: '/hiring/v2/employer/kpi-header' },
    { pattern: /^\/jobs\/employer\/copilot\/([^/]+)\/suggestions$/, replacement: '/hiring/v2/employer/copilot/$1/suggestions' },
    { pattern: /^\/jobs\/employer\/scorecards\/([^/]+)$/, replacement: '/hiring/v2/employer/scorecards/$1' },
    { pattern: /^\/jobs\/employer\/auto-scheduler\/([^/]+)\/suggest$/, replacement: '/hiring/v2/employer/auto-scheduler/$1/suggest' },
    { pattern: /^\/jobs\/employer\/communication-sequences\/([^/]+)$/, replacement: '/hiring/v2/employer/communication-sequences/$1' },
    { pattern: /^\/jobs\/employer\/hiring-forecast$/, replacement: '/hiring/v2/employer/hiring-forecast' },
    { pattern: /^\/jobs\/employer\/talent-rediscovery$/, replacement: '/hiring/v2/employer/talent-rediscovery' },
    { pattern: /^\/jobs\/alerts$/, replacement: '/hiring/v2/candidate/alerts' },
    { pattern: /^\/jobs\/alerts\/preferences$/, replacement: '/hiring/v2/candidate/alerts/preferences' },

    { pattern: /^\/employers\/my-application$/, replacement: '/hiring/v2/employer/application/current' },
    { pattern: /^\/employers\/my-permissions$/, replacement: '/hiring/v2/employer/application/permissions' },
    { pattern: /^\/employers\/reverify-status$/, replacement: '/hiring/v2/employer/application/reverify-status' },
    { pattern: /^\/employers\/messages\/([^/]+)$/, replacement: '/hiring/v2/employer/application/messages/$1' },
    { pattern: /^\/employers\/documents\/([^/]+)\/([^/]+)\/download$/, replacement: '/hiring/v2/employer/application/documents/$1/$2/download' },
    { pattern: /^\/employers\/admin\/stats$/, replacement: '/hiring/v2/admin/employers/stats' },
    { pattern: /^\/employers\/admin\/applications$/, replacement: '/hiring/v2/admin/employers/applications' },
    { pattern: /^\/employers\/admin\/application\/([^/]+)$/, replacement: '/hiring/v2/admin/employers/application/$1' },
    { pattern: /^\/employers\/admin\/command-center$/, replacement: '/hiring/v2/admin/employers/command-center' },
    { pattern: /^\/employers\/admin\/communications\/([^/]+)$/, replacement: '/hiring/v2/admin/employers/communications/$1' },
  ];

  for (const rule of rules) {
    if (rule.pattern.test(pathOnly)) {
      return pathOnly.replace(rule.pattern, rule.replacement) + queryOnly;
    }
  }

  return url;
}

async function request(
  method: string,
  url: string,
  data?: any,
  config: RequestConfig = {},
): Promise<{ data: any; status: number; headers: Headers }> {
  if (!BACKEND_ORIGIN_CONSISTENCY.ok) {
    throw new ApiError(
      `Platform backend origin mismatch: ${BACKEND_ORIGIN_CONSISTENCY.issues.join(' ')}`,
      {
        data: {
          detail: 'PLATFORM_BACKEND_ORIGIN_MISMATCH',
          issues: BACKEND_ORIGIN_CONSISTENCY.issues,
          react_base: BACKEND_ORIGIN_CONSISTENCY.reactBase,
          expo_base: BACKEND_ORIGIN_CONSISTENCY.expoBase,
          canonical_base: BACKEND_ORIGIN_CONSISTENCY.canonicalBase,
        },
        status: 500,
        headers: new Headers(),
      },
      { method, url }
    );
  }

  const rewrittenUrl = rewriteFeature26LegacyReadUrl(method, url);

  // Build URL
  let fullUrl = rewrittenUrl.startsWith('http') ? rewrittenUrl : `${BASE_URL}${rewrittenUrl}`;
  if (config.params) {
    const qs = new URLSearchParams(
      Object.entries(config.params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)])
    ).toString();
    if (qs) fullUrl += (fullUrl.includes('?') ? '&' : '?') + qs;
  }

  // Strict scope guard: user-path clients must never depend on admin plans endpoint.
  if (
    fullUrl.includes('/api/admin/subscriptions/plans')
    && !config.allowAdminSubscriptionPlansEndpoint
  ) {
    throw new ApiError(
      'Admin-only endpoint blocked in user path. Use /api/subscriptions/plans.',
      {
        data: {
          code: 'ADMIN_ENDPOINT_SCOPE_BLOCKED',
          detail: 'Use /api/subscriptions/plans for user-facing plan reads',
          blocked_endpoint: '/api/admin/subscriptions/plans',
          replacement_endpoint: '/api/subscriptions/plans',
        },
        status: 400,
        headers: new Headers(),
      },
      { method, url: fullUrl }
    );
  }

  const dedupeKey = method.toUpperCase() === 'GET' && !config.skipDedupe && !config.onUploadProgress
    && !isFreshnessCriticalEndpoint(fullUrl)
    ? `${fullUrl}::${config.responseType || 'json'}`
    : '';
  const isAdminGet = method.toUpperCase() === 'GET' && fullUrl.includes('/api/admin/');
  const adminRateLimitKey = isAdminGet ? 'GET::/api/admin/*' : '';

  const lowPriorityTtl = method.toUpperCase() === 'GET' && !config.skipDedupe && !isFreshnessCriticalEndpoint(fullUrl)
    ? getLowPriorityCacheTtl(fullUrl)
    : 0;
  const now = Date.now();
  const endpointRateLimitKey = `${method.toUpperCase()}::${normalizeNetworkIssueUrl(fullUrl)}`;
  const preemptiveNoisyCooldownMs = getPreemptiveNoisyEndpointCooldown(fullUrl, method);
  const optionalForbiddenCooldown = getOptionalForbiddenCooldown(fullUrl, method);
  const cachedLowPriority = dedupeKey ? lowPriorityCache.get(dedupeKey) : null;
  if (cachedLowPriority && cachedLowPriority.expiresAt > now) {
    return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
  }

  const forbiddenUntil = optionalForbiddenCooldown
    ? (forbiddenCooldownUntil.get(optionalForbiddenCooldown.key) || 0)
    : 0;
  if (optionalForbiddenCooldown && forbiddenUntil > now) {
    if (method.toUpperCase() === 'GET') {
      if (cachedLowPriority && cachedLowPriority.expiresAt > now) {
        return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
      }
      return {
        data: { suppressed: true, reason: 'forbidden_cooldown' },
        status: 204,
        headers: new Headers(),
      };
    }

    return {
      data: { suppressed: true, reason: 'forbidden_cooldown' },
      status: 202,
      headers: new Headers(),
    };
  }

  const backoffUntil = dedupeKey ? rateLimitedUntil.get(dedupeKey) || 0 : 0;
  if (dedupeKey && backoffUntil > now) {
    if (cachedLowPriority) {
      return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
    }
    return {
      data: { suppressed: true, reason: 'rate_limited_cooldown' },
      status: 204,
      headers: new Headers(),
    };
  }

  const endpointBackoffUntil = rateLimitedUntil.get(endpointRateLimitKey) || 0;
  if (endpointBackoffUntil > now) {
    if (method.toUpperCase() === 'GET') {
      if (cachedLowPriority && cachedLowPriority.expiresAt > now) {
        return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
      }
      return {
        data: { suppressed: true, reason: 'rate_limited_cooldown' },
        status: 204,
        headers: new Headers(),
      };
    }

    return {
      data: { suppressed: true, reason: 'rate_limited_cooldown' },
      status: 202,
      headers: new Headers(),
    };
  }

  if (preemptiveNoisyCooldownMs > 0) {
    const endpointNoisyUntil = noisyEndpointCooldownUntil.get(endpointRateLimitKey) || 0;
    if (endpointNoisyUntil > now) {
      if (method.toUpperCase() === 'GET') {
        if (cachedLowPriority && cachedLowPriority.expiresAt > now) {
          return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
        }
        return {
          data: { suppressed: true, reason: 'preemptive_noisy_cooldown' },
          status: 204,
          headers: new Headers(),
        };
      }
      return {
        data: { suppressed: true, reason: 'preemptive_noisy_cooldown' },
        status: 202,
        headers: new Headers(),
      };
    }
    noisyEndpointCooldownUntil.set(endpointRateLimitKey, now + preemptiveNoisyCooldownMs);
  }

  const adminBackoffUntil = adminRateLimitKey ? rateLimitedUntil.get(adminRateLimitKey) || 0 : 0;
  if (adminRateLimitKey && adminBackoffUntil > now) {
    if (cachedLowPriority) {
      return { data: cachedLowPriority.data, status: cachedLowPriority.status, headers: cachedLowPriority.headers };
    }
    throw new ApiError('Admin API cooling down after rate-limit', {
      status: 429,
      data: { detail: 'Admin endpoints temporarily cooling down after rate limiting.' },
      headers: new Headers(),
    });
  }

  if (dedupeKey && !config._retryCount && inFlightGetRequests.has(dedupeKey)) {
    recordShellHealthMetric('dedupe_hits', { url: fullUrl });
    return inFlightGetRequests.get(dedupeKey)!;
  }

  const executeRequest = async () => {
    const loadingTicket = config.silentLoading ? null : beginGlobalLoading(method === 'GET' ? 'fetch' : 'mutation');

    // Build headers
    const headers: Record<string, string> = {
      Accept: 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      ...buildObservabilityHeaders(),
      ...(config.headers || {}),
    };

    if (typeof window !== 'undefined') {
      headers['X-Requested-With'] = 'XMLHttpRequest';
      const csrfToken = readCookieValue('csrf_token') || readCookieValue('csrftoken') || readCookieValue('csrf');
      if (csrfToken && !headers['X-CSRF-Token']) {
        headers['X-CSRF-Token'] = csrfToken;
      }
      try {
        const locale = Intl.DateTimeFormat().resolvedOptions().locale || navigator.language || '';
        const languages = Array.isArray(navigator.languages) ? navigator.languages.join(',') : (navigator.language || '');
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
        if (locale) headers['X-User-Locale'] = locale;
        if (navigator.language) headers['X-Browser-Language'] = navigator.language;
        if (languages) headers['X-Browser-Languages'] = languages;
        if (timezone) headers['X-Browser-Timezone'] = timezone;
      } catch (error) { handleAppRecoverableError({ scope: 'src/services/api.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      if (isFreshnessCriticalEndpoint(fullUrl) && method.toUpperCase() === 'GET') {
        headers['Cache-Control'] = 'no-cache, no-store, max-age=0';
        headers.Pragma = 'no-cache';
      }
    }

    headers['X-Client-Platform'] = Platform.OS === 'web' ? 'web' : 'mobile';

    // Auth token
    const token = await getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    // Build fetch options
    const fetchOptions: RequestInit = { method, headers, credentials: 'include' };

    if (data !== undefined && data !== null) {
      if (data instanceof FormData) {
        // Let browser set Content-Type with boundary for FormData
        fetchOptions.body = data;
      } else {
        headers['Content-Type'] = 'application/json';
        fetchOptions.body = JSON.stringify(data);
      }
    }

    // For uploads with progress tracking, use XMLHttpRequest
    if (config.onUploadProgress && data instanceof FormData) {
      return xhrUpload(method, fullUrl, data, headers, config);
    }

    // Timeout via AbortController
    const controller = new AbortController();
    const timeout = config.timeout || (
      method.toUpperCase() === 'GET'
        ? (config.responseType === 'blob' ? DEFAULT_BINARY_GET_TIMEOUT : DEFAULT_GET_TIMEOUT)
        : DEFAULT_MUTATION_TIMEOUT
    );
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    fetchOptions.signal = controller.signal;

    try {
      const response = await fetch(fullUrl, fetchOptions);
      clearTimeout(timeoutId);

      // Parse response body
      let responseData: any;
      if (config.responseType === 'blob') {
        responseData = await response.blob();
      } else if (config.responseType === 'text') {
        responseData = await response.text();
      } else {
        const text = await response.text();
        try { responseData = JSON.parse(text); } catch { responseData = text; }
      }

      const result = { data: responseData, status: response.status, headers: response.headers };

      if (!response.ok) {
        const policyGatePayload = extractPolicyGatePayload(responseData);
        const isPolicyGateBlocked = Boolean(policyGatePayload);
        if ((response.status === 429 || response.status >= 500) && !isPolicyGateBlocked) {
          emitNetworkIssue({ status: response.status, url: fullUrl, reason: response.status === 429 ? 'rate_limited' : 'server_error' });
        }
        const error = new ApiError(`Request failed with status ${response.status}`, result);
        throw error;
      }

      if (dedupeKey && lowPriorityTtl > 0) {
        lowPriorityCache.set(dedupeKey, {
          data: responseData,
          status: response.status,
          headers: response.headers,
          expiresAt: Date.now() + lowPriorityTtl,
        });
        rateLimitedUntil.delete(dedupeKey);
      }

      return result;
    } catch (err: any) {
      clearTimeout(timeoutId);

      if (err?.name === 'AbortError') {
        // Suppress network issue signals for fire-and-forget telemetry endpoints
        const isTelemetry = ['/vitals/', '/session-replay/', '/platform-shell-health/', '/vanity-metrics'].some(p => fullUrl.includes(p));
        if (!isTelemetry) {
          emitNetworkIssue({ status: 0, url: fullUrl, reason: 'timeout' });
        }
      }

      // Handle response interceptor logic
      if (err instanceof ApiError && err.response) {
        const status = err.response.status;

        const policyGatePayload = extractPolicyGatePayload(err.response.data);
        const platformControlPayload = extractPlatformControlPayload(err.response.data);

        if ((status === 503 || status === 423) && platformControlPayload && typeof window !== 'undefined') {
          try {
            window.dispatchEvent(new CustomEvent('app-platform-control-blocked', {
              detail: {
                ...platformControlPayload,
                status,
                url: normalizeNetworkIssueUrl(fullUrl),
                timestamp: Date.now(),
              },
            }));
          } catch (error) { handleAppRecoverableError({ scope: 'src/services/api.ts#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }

        if ((status >= 500 || status === 429) && !policyGatePayload) {
          emitNetworkIssue({ status, url: fullUrl, reason: status === 429 ? 'rate_limited' : 'server_error' });
        }

        if ((status === 403 || status === 503) && policyGatePayload) {
          err.policyGateBlocked = true;
          err.policyGateReason = policyGatePayload.reason_code || 'security_prerequisites_failed';
          err.policyGateFailedChecks = Array.isArray(policyGatePayload.failed_checks) ? policyGatePayload.failed_checks : [];
          err.policyGateDecisionId = policyGatePayload.decision_id || '';
          if (typeof window !== 'undefined') {
            try {
              window.dispatchEvent(new CustomEvent('app-policy-gate-blocked', {
                detail: {
                  reasonCode: err.policyGateReason,
                  failedChecks: err.policyGateFailedChecks,
                  decisionId: err.policyGateDecisionId,
                  status,
                  url: normalizeNetworkIssueUrl(fullUrl),
                  timestamp: Date.now(),
                },
              }));
            } catch (error) { handleAppRecoverableError({ scope: 'src/services/api.ts#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          }
        }

        // 401: clear token only for confirmed auth-session invalidation
        if (status === 401) {
          const reasonCode = extractStructuredErrorCode(err.response.data) || 'unauthorized';
          const shouldReset = shouldResetTokenOn401(fullUrl, err.response.data);
          err.authUnauthorized = true;
          err.authErrorCode = reasonCode;
          err.authEndpoint = normalizeNetworkIssueUrl(fullUrl);

          if (shouldReset) {
            cachedToken = null;
            await AsyncStorage.removeItem('session_token').catch(() => {});
            if (Platform.OS !== 'web') {
              await secureClearToken();
            }
            if (typeof window !== 'undefined') {
              try {
                window.localStorage.removeItem('session_token');
              } catch (error) { handleAppRecoverableError({ scope: 'src/services/api.ts#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
            }
          }

          emitAuthUnauthorized({ url: fullUrl, reasonCode });
          throw err;
        }

        // 403: subscription enforcement
        if (status === 403) {
          const respData = err.response.data;
          const sub = (respData?.error === 'Subscription Required') ? respData
            : (respData?.detail?.error === 'Subscription Required') ? respData.detail
            : null;
          if (sub) {
            err.subscriptionRequired = true;
            err.requiredPlan = sub.required_plan;
            err.currentPlan = sub.current_plan;
            err.upgradeUrl = sub.upgrade_url;
            err.subscriptionMessage = sub.message;
            if (shouldEmitSubscriptionUpgradePrompt(config, fullUrl, method)) {
              try {
                // eslint-disable-next-line @typescript-eslint/no-require-imports
                const { subscriptionUpgradeEmitter } = require('../components/SubscriptionUpgradeModal');
                subscriptionUpgradeEmitter.emit({
                  requiredPlan: sub.required_plan || 'basic',
                  currentPlan: sub.current_plan || 'free',
                  message: sub.message || 'This feature requires a higher plan.',
                  endpoint: normalizeNetworkIssueUrl(fullUrl),
                  method: String(method || 'GET').toUpperCase(),
                  source: 'auto_api',
                });
              } catch { /* modal not mounted yet */ }
            }
          }
        }

        // Retry logic for 5xx GET requests
        const isRetryable = status >= 500 && status < 600;
        const isGet = method.toUpperCase() === 'GET';
        const retryCount = config._retryCount || 0;

        if (isRetryable && isGet && retryCount < MAX_RETRIES) {
          const delay = RETRY_DELAY_BASE * Math.pow(2, retryCount);
          await new Promise(resolve => setTimeout(resolve, delay));
          return request(method, url, data, { ...config, _retryCount: retryCount + 1 });
        }

        if (status === 429) {
          recordShellHealthMetric('rate_limit_429s', { url: fullUrl, status });
          const quotaPayload = err.response?.data;
          if (quotaPayload && quotaPayload.error_code === 'feature_daily_limit_reached') {
            emitFeatureQuotaLimit({
              featureKey: String(quotaPayload.feature_key || ''),
              used: Number(quotaPayload.used || 0),
              limit: Number(quotaPayload.limit || 0),
            });
          }
          const retryAfterMs = getRetryAfterMs(err.response?.headers);
          const hardCooldownMs = getHard429Cooldown(fullUrl, method);
          const cooldownMs = Math.max(retryAfterMs, hardCooldownMs, isBackgroundProbe(fullUrl) ? 120_000 : 30_000);
          rateLimitedUntil.set(endpointRateLimitKey, Date.now() + cooldownMs);
          if (dedupeKey) {
            rateLimitedUntil.set(dedupeKey, Date.now() + cooldownMs);
            const cached = lowPriorityCache.get(dedupeKey);
            if (cached) {
              return { data: cached.data, status: cached.status, headers: cached.headers };
            }
          }
          if (adminRateLimitKey) {
            rateLimitedUntil.set(adminRateLimitKey, Date.now() + cooldownMs);
          }

          if (optionalForbiddenCooldown) {
            forbiddenCooldownUntil.set(optionalForbiddenCooldown.key, Date.now() + optionalForbiddenCooldown.cooldownMs);
          }
        }

        if (status === 403 && optionalForbiddenCooldown) {
          forbiddenCooldownUntil.set(optionalForbiddenCooldown.key, Date.now() + optionalForbiddenCooldown.cooldownMs);
        }
      }

      // Network error retry for GET requests
      if (!err.response && method.toUpperCase() === 'GET') {
        emitNetworkIssue({ status: 0, url: fullUrl, reason: 'network_error' });
        const retryCount = config._retryCount || 0;
        if (retryCount < MAX_RETRIES) {
          const delay = RETRY_DELAY_BASE * Math.pow(2, retryCount);
          await new Promise(resolve => setTimeout(resolve, delay));
          return request(method, url, data, { ...config, _retryCount: retryCount + 1 });
        }
      }

      throw err;
    } finally {
      endGlobalLoading(loadingTicket);
    }
  };

  const requestPromise = executeRequest();
  if (dedupeKey) {
    inFlightGetRequests.set(dedupeKey, requestPromise);
    requestPromise.finally(() => {
      if (inFlightGetRequests.get(dedupeKey) === requestPromise) {
        inFlightGetRequests.delete(dedupeKey);
      }
    }).catch(() => {
      // Prevent background/deduped rejected GET cleanup promises from surfacing
      // as unhandled PAGE ERROR noise; the original requestPromise still rejects
      // to its caller for intentional handling.
    });
  }

  return requestPromise;
}

// ── XHR upload with progress tracking ───────────────────────────────────
function xhrUpload(
  method: string,
  url: string,
  data: FormData,
  headers: Record<string, string>,
  config: RequestConfig,
): Promise<{ data: any; status: number; headers: Headers }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);

    for (const [key, value] of Object.entries(headers)) {
      if (key.toLowerCase() !== 'content-type') {
        xhr.setRequestHeader(key, value);
      }
    }

    if (config.onUploadProgress) {
      xhr.upload.onprogress = (event) => {
        config.onUploadProgress!({ loaded: event.loaded, total: event.total });
      };
    }

    xhr.onload = () => {
      let responseData: any;
      try { responseData = JSON.parse(xhr.responseText); } catch { responseData = xhr.responseText; }

      const result = { data: responseData, status: xhr.status, headers: new Headers() };

      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(result);
      } else {
        reject(new ApiError(`Request failed with status ${xhr.status}`, result));
      }
    };

    xhr.onerror = () => reject(new ApiError('Network error'));
    xhr.ontimeout = () => reject(new ApiError('Request timeout'));
    xhr.timeout = config.timeout || DEFAULT_MUTATION_TIMEOUT;
    xhr.send(data);
  });
}

// ── API client object (drop-in replacement for axios instance) ──────────
const api = {
  get: (url: string, config?: RequestConfig) =>
    request('GET', url, undefined, config),

  post: (url: string, data?: any, config?: RequestConfig) =>
    request('POST', url, data, config),

  put: (url: string, data?: any, config?: RequestConfig) =>
    request('PUT', url, data, config),

  patch: (url: string, data?: any, config?: RequestConfig) =>
    request('PATCH', url, data, config),

  delete: (url: string, config?: RequestConfig) =>
    request('DELETE', url, undefined, config),

  // Backward-compatible properties used by components for URL construction
  defaults: {
    baseURL: BASE_URL,
    headers: {
      common: {
        get Authorization() {
          if (WEB_COOKIE_ONLY_AUTH && typeof window !== 'undefined') return '';
          return cachedToken ? `Bearer ${cachedToken}` : '';
        },
      },
    },
  },
};

// === Simple in-memory cache for GET requests ===
const cache = new Map<string, { data: any; timestamp: number }>();
const CACHE_TTL = 60000; // 1 minute

export const cachedGet = async (url: string, ttl = CACHE_TTL) => {
  const now = Date.now();
  const cached_entry = cache.get(url);
  if (cached_entry && (now - cached_entry.timestamp) < ttl) {
    return cached_entry.data;
  }
  const response = await api.get(url);
  cache.set(url, { data: response.data, timestamp: now });
  return response.data;
};

export const clearCache = (url?: string) => {
  if (url) {
    cache.delete(url);
    for (const key of lowPriorityCache.keys()) {
      if (key.includes(url)) {
        lowPriorityCache.delete(key);
      }
    }
    for (const key of inFlightGetRequests.keys()) {
      if (key.includes(url)) {
        inFlightGetRequests.delete(key);
      }
    }
    for (const key of rateLimitedUntil.keys()) {
      if (key.includes(url)) {
        rateLimitedUntil.delete(key);
      }
    }
    return;
  }

  cache.clear();
  lowPriorityCache.clear();
  inFlightGetRequests.clear();
  rateLimitedUntil.clear();
};

export const clearGatewayRuntimeCaches = () => {
  clearCache('/subscriptions/gateway-config');
  clearCache('/subscriptions/mobile-money/sandbox-info');
  clearCache('/subscriptions/mobile-money/gateways');
};

const clearFreshnessCriticalCaches = () => {
  for (const endpoint of FRESHNESS_CRITICAL_ENDPOINT_PATTERNS) {
    clearCache(endpoint);
  }
};

let freshnessGuardInitialized = false;

const initFreshnessGuard = () => {
  if (freshnessGuardInitialized || typeof window === 'undefined') {
    return;
  }
  freshnessGuardInitialized = true;

  const onVisible = () => {
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
      return;
    }
    clearFreshnessCriticalCaches();
  };

  window.addEventListener('focus', onVisible);
  window.addEventListener('online', onVisible);
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisible);
  }
};

initFreshnessGuard();

// === Exported API functions with caching ===

export const getScenarios = async (category?: string) => {
  const key = category ? `/scenarios?category=${category}` : '/scenarios';
  return cachedGet(key, 120000);
};

export const getScenario = async (scenarioId: string) => {
  return cachedGet(`/scenarios/${scenarioId}`, 300000);
};

export const startConversation = async (userId: string, scenarioId: string) => {
  const response = await api.post('/conversations/start', {
    user_id: userId,
    scenario_id: scenarioId,
  });
  return response.data;
};

export const sendMessage = async (conversationId: string, userId: string, message: string) => {
  const response = await api.post('/conversations/message', {
    conversation_id: conversationId,
    user_id: userId,
    message,
  });
  return response.data;
};

export const completeConversation = async (conversationId: string, userId: string) => {
  const response = await api.post(`/conversations/${conversationId}/complete?user_id=${userId}`);
  return response.data;
};

export const getUserConversations = async (userId: string, status?: string) => {
  const params = status ? { status } : {};
  const response = await api.get(`/conversations/${userId}`, { params });
  return response.data;
};

export const getConversation = async (conversationId: string) => {
  const response = await api.get(`/conversation/${conversationId}`);
  return response.data;
};

export const getProgress = async (userId: string) => {
  return cachedGet(`/progress/${userId}`, 30000);
};

export const getDailyTip = async () => {
  return cachedGet('/daily-tip', 300000);
};

export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export default api;
