import { usePathname } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { recordShellHealthEvent, recordShellHealthMetric } from '../services/shellHealthMonitor';
import { useAuth } from '../context/AuthContext';

type UiGuardContract = {
  routeKey: string;
  matches: (pathname: string) => boolean;
  requiredTexts?: string[];
  requiredSelectors?: string[];
  delayMs: number;
  extraCheck?: (bodyText: string, doc: Document) => Record<string, any>;
};

const LOGIN_METHOD_LABELS = ['Google', 'Microsoft', 'Apple', 'PIN', 'Passkey', 'QR Login'];

const CONTRACTS: UiGuardContract[] = [
  {
    routeKey: 'login',
    matches: (pathname) => pathname === '/auth/login' || pathname === '/login',
    requiredTexts: ['Welcome Back', ...LOGIN_METHOD_LABELS],
    requiredSelectors: ['[data-testid="login-screen"]', '[data-testid="login-submit-button"]'],
    delayMs: 3500,
    extraCheck: (bodyText) => {
      const visibleMethods = LOGIN_METHOD_LABELS.filter((label) => bodyText.includes(label));
      return {
        visible_auth_methods: visibleMethods,
        visible_auth_method_count: visibleMethods.length,
        auth_layout_mode: 'always-visible-grid',
      };
    },
  },
  {
    routeKey: 'welcome',
    matches: (pathname) => pathname === '/' || pathname === '/welcome',
    requiredTexts: ['Track Every Dimension of Growth', 'REAL-TIME ANALYTICS'],
    requiredSelectors: ['[data-testid="welcome-screen"]', '[data-testid="welcome-nav"]'],
    delayMs: 3500,
  },
  {
    routeKey: 'dashboard-home',
    matches: (pathname) => pathname === '/dashboard' || pathname === '/(tabs)' || pathname === '/home',
    requiredTexts: ['Data refreshes automatically every 30 seconds'],
    requiredSelectors: ['[data-testid="home-screen"]'],
    delayMs: 5000,
  },
  {
    routeKey: 'ai-learning-hub',
    matches: (pathname) => pathname.startsWith('/ai-learning-hub'),
    requiredTexts: ['AI Learning Hub'],
    requiredSelectors: ['[data-testid="ai-learning-hub-page-root"]', '[data-testid="ai-learning-hub-heading"]'],
    delayMs: 6500,
  },
  {
    routeKey: 'certificate-gallery',
    matches: (pathname) => pathname.startsWith('/certificate-gallery'),
    requiredTexts: ['CERTIFICATE GALLERY'],
    requiredSelectors: ['[data-testid="certificate-gallery-page"]', '[data-testid="certificate-gallery-title"]'],
    delayMs: 5000,
  },
  {
    routeKey: 'certificate-operations',
    matches: (pathname) => pathname.startsWith('/certificate-operations'),
    requiredTexts: ['CERTIFICATE OPERATIONS'],
    requiredSelectors: ['[data-testid="certificate-operations-page"]', '[data-testid="certificate-operations-title"]'],
    delayMs: 6000,
  },
  {
    routeKey: 'admin-console',
    matches: (pathname) => pathname.startsWith('/admin-console'),
    requiredTexts: ['Operations Console', 'AI Command Center'],
    delayMs: 8000,
  },
];

export function useUiRouteGuards() {
  const pathname = usePathname();
  const lastSignatureRef = useRef('');
  const lastStatusByRouteRef = useRef<Record<string, string>>({});
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') return;
    const contract = CONTRACTS.find((item) => item.matches(pathname));
    if (!contract) return;

    const timer = window.setTimeout(() => {
      const bodyText = document.body?.innerText || '';
      const requiredTexts = contract.requiredTexts || [];
      const requiredSelectors = contract.requiredSelectors || [];
      const missingTexts = requiredTexts.filter((label) => !bodyText.includes(label));
      const missingSelectors = requiredSelectors.filter((selector) => !document.querySelector(selector));
      const extra = contract.extraCheck ? contract.extraCheck(bodyText, document) : {};
      const optionCount = typeof extra.visible_auth_method_count === 'number' ? extra.visible_auth_method_count : undefined;
      const status = missingTexts.length === 0 && missingSelectors.length === 0 && (optionCount === undefined || optionCount >= 6) ? 'healthy' : 'failed';
      const payload = {
        route_key: contract.routeKey,
        status,
        auth_state: isAuthenticated ? 'authenticated' : 'public',
        missing_texts: missingTexts,
        missing_selectors: missingSelectors,
        required_texts: requiredTexts,
        required_selectors: requiredSelectors,
        viewport: { width: window.innerWidth, height: window.innerHeight },
        ...extra,
      };
      const signature = JSON.stringify({ pathname, ...payload });
      if (signature === lastSignatureRef.current) return;
      lastSignatureRef.current = signature;
      const previousStatus = lastStatusByRouteRef.current[contract.routeKey];
      lastStatusByRouteRef.current[contract.routeKey] = status;
      if (isAuthenticated && status === 'failed') {
        recordShellHealthEvent('post_login_route_failure', payload);
      }
      if (previousStatus === 'failed' && status === 'healthy') {
        recordShellHealthMetric('route_recoveries', { route_key: contract.routeKey, auth_state: isAuthenticated ? 'authenticated' : 'public', source: 'ui_route_guard' });
      }
      recordShellHealthEvent('ui_route_guard', payload);
    }, contract.delayMs);

    return () => window.clearTimeout(timer);
  }, [isAuthenticated, pathname]);
}