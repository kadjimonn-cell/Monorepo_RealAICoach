import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, Platform, useWindowDimensions } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api, { setCachedToken } from '../../../services/api';
import { useAuth } from '../../../context/AuthContext';
import { useTheme } from '../../../context/ThemeContext';
import { useTranslation } from '../../../hooks/useTranslation';
import { getLandingRouteForRole } from '../../../lib/platformRoleLanding';
import { hasKnownTopLevelSegment, normalizeIncomingSystemPath } from '../../../utils/routeResolution';
import { resolveRuntimeBaseUrl } from '../../../utils/runtimeBaseUrl';
import { isTrustedSsoMessageOrigin, resolveSsoPopupTargetOrigin } from '../../../utils/ssoMessagingSecurity';
import { clientLogger } from '../../../utils/clientLogger';
import { serializeWebAuthnCredential } from '../../../utils/webauthn';
import { getStrength } from './passwordStrength';
import { makeStyles } from './loginStyles';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';
import { isValidAuthQrPayload, normalizeAuthQrPayload } from './authQrContract';

export function useLoginController(forceCompactMode = false) {
  const router = useRouter();
  const { reset, logout: logoutParam, return_to: returnToParam } = useLocalSearchParams<{ reset?: string | string[]; logout?: string | string[]; return_to?: string | string[] }>();
  const { user, login, verify2FA, loginWithGoogle, loginWithMicrosoft, requestOtp, loginWithOtp, loading, refreshUser } = useAuth();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const { darkMode, colors, setThemeMode } = useTheme();
  const T = {
    bg: colors.bg, bgAlt: colors.bgAlt, bgCard: colors.card,
    text: colors.text, text2: colors.textSec, text3: colors.textMuted,
    gray300: colors.textSec, gray400: colors.textMuted,
    cyan: colors.accent, neonBlue: colors.primary, teal: colors.accent, purple: colors.purple,
    success: colors.success, error: colors.error, warning: colors.warning,
    errorText: colors.errorText, successText: colors.successText, infoText: colors.infoText,
    warningText: (colors as any).warningText || colors.warning, purpleText: (colors as any).purpleText || colors.purple,
    glassBorder: colors.glassBorder, glassSurface: colors.glassSurface, glassHL: colors.hover,
    // In dark mode: white text on dark cards. In light mode: use primary text (dark navy) so
    // it stays readable on light card/bg surfaces (e.g. logo, modal title, success overlay).
    white: colors.text,
    onPrimary: colors.primaryText,
    overlay: colors.overlay,
    isDark: darkMode,
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const s = useMemo(() => makeStyles(T), [colors, darkMode]);
  const webOrigin = Platform.OS === 'web' && typeof window !== 'undefined'
    ? window.location.origin.replace(/\/+$/, '')
    : '';
  const liveApiBase = resolveRuntimeBaseUrl(undefined, webOrigin);
  const webAssetBase = (liveApiBase || process.env.REACT_APP_BACKEND_URL || '').replace(/\/+$/, '');
  const isDesktop = width >= 960;
  const isTablet = width >= 640 && width < 960;
  const isMobile = width < 640;
  const isCompactMobile = width < 420;
  const isUltraCompact = forceCompactMode || width <= 420;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const headingText = t('login.heading');
  const subheadingText = t('login.subheading');

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const SSO_ERROR_MESSAGES: Record<string, string> = {
    not_configured: tx('login.sso.notConfigured', 'SSO login is not configured. Please contact support.'),
    apple_not_configured: tx('login.sso.appleNotConfigured', 'Apple login is not configured. Please contact support.'),
    apple_provider_verification_required: tx('login.sso.appleProviderVerificationRequired', 'Apple login is blocked until this callback base is verified in Apple Developer Console. Please register the exact callback URL shown in SSO Status.'),
    apple_callback_not_provider_registered: tx('login.sso.appleCallbackNotProviderRegistered', 'Apple login is temporarily blocked: this environment callback is not currently registered in Apple Developer Service ID return URLs.'),
    apple_broker_invalid_target: tx('login.sso.appleBrokerInvalidTarget', 'Apple login relay target was invalid for this environment. Please retry from the active preview URL.'),
    unavailable: tx('login.sso.unavailable', 'SSO login is temporarily unavailable. Please try again later.'),
    invalid_request: tx('login.sso.invalidRequest', 'The sign-in provider rejected the redirect or callback for this window. Open the provider in a full browser window, or verify the exact callback URL in the provider portal.'),
    token_failed: tx('login.sso.tokenFailed', 'Authentication failed. Please try again.'),
    graph_failed: tx('login.sso.graphFailed', 'Could not retrieve your profile. Please try again.'),
    no_code: tx('login.sso.noCode', 'Login was cancelled or failed. Please try again.'),
    no_id_token: tx('login.sso.noIdToken', 'Apple login failed — no identity token received.'),
    no_email: tx('login.sso.noEmail', 'Apple login failed — email not provided.'),
    internal: tx('login.sso.internal', 'An unexpected error occurred during login.'),
  };

  const getInitialError = (): string => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        const ssoErr = urlParams.get('sso_error');
        if (ssoErr && SSO_ERROR_MESSAGES[ssoErr]) return SSO_ERROR_MESSAGES[ssoErr];
        if (ssoErr) return tx('login.errors.failedTryAgain', 'Login failed. Please try again.');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return '';
  };

  const getInitialSsoError = (): string | null => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        return new URLSearchParams(window.location.search).get('sso_error');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return null;
  };

  const getInitialLogoutLanding = (): boolean => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        return new URLSearchParams(window.location.search).get('logout') === '1';
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return false;
  };

  const [error, setError] = useState(getInitialError);
  const [postResetBanner, setPostResetBanner] = useState(Array.isArray(reset) ? reset[0] === 'success' : reset === 'success');
  const [authRecovery, setAuthRecovery] = useState<any>(null);
  const [ssoErrorCode, setSsoErrorCode] = useState<string | null>(getInitialSsoError);
  const [show2FA, setShow2FA] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [pending2FAUserId, setPending2FAUserId] = useState('');
  const [pendingAuthEmail, setPendingAuthEmail] = useState('');
  const [pendingAuthPassword, setPendingAuthPassword] = useState('');
  const [pendingRememberMe, setPendingRememberMe] = useState(false);
  const [otpHint, setOtpHint] = useState('');
  const [loginMethod, setLoginMethod] = useState<'password' | 'otp'>('password');
  const [otpLoginCode, setOtpLoginCode] = useState('');
  const [otpLoginHint, setOtpLoginHint] = useState('');
  const [otpLoginRequested, setOtpLoginRequested] = useState(false);
  const [otpLoginLoading, setOtpLoginLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [altMode, setAltMode] = useState<'none' | 'pin' | 'passkey'>('none');
  const [pin, setPin] = useState('');
  const [userHasPasskey, setUserHasPasskey] = useState<boolean | null>(null); // null = not checked, true/false = checked
  const [showPasskeyEnrollmentPrompt, setShowPasskeyEnrollmentPrompt] = useState(false);
  const [passkeyPromptPendingRoute, setPasskeyPromptPendingRoute] = useState('');
  const [passkeyPromptBusy, setPasskeyPromptBusy] = useState(false);
  const [recoveryCountdown, setRecoveryCountdown] = useState(0);
  const [postLogoutBanner, setPostLogoutBanner] = useState(getInitialLogoutLanding);
  const [logoutRedirectHold, setLogoutRedirectHold] = useState(getInitialLogoutLanding);
  const logoutBannerTelemetryTrackedRef = useRef(false);
  const isPostPasswordReset = Platform.OS === 'web' && typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('reset') === 'success'
    : false;
  const [showResetSuccess, setShowResetSuccess] = useState(isPostPasswordReset);

  const getWebInputValue = useCallback((testId: string, placeholder?: string): string => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return '';
    try {
      const direct = document.querySelector(`[data-testid="${testId}"]`) as HTMLInputElement | null;
      if (direct && typeof direct.value === 'string' && direct.value.trim()) return direct.value.trim();

      const nested = document.querySelector(`[data-testid="${testId}"] input`) as HTMLInputElement | null;
      if (nested && typeof nested.value === 'string' && nested.value.trim()) return nested.value.trim();

      if (placeholder) {
        const byPlaceholder = document.querySelector(`input[placeholder="${placeholder}"]`) as HTMLInputElement | null;
        if (byPlaceholder && typeof byPlaceholder.value === 'string' && byPlaceholder.value.trim()) return byPlaceholder.value.trim();
      }
    } catch {
      return '';
    }
    return '';
  }, []);

  const clearAuthIssue = useCallback(() => {
    setError('');
    setAuthRecovery(null);
    setRecoveryCountdown(0);
  }, []);

  const emitLogoutBannerTelemetry = useCallback((event: 'shown' | 'dismissed') => {
    const routePath = Platform.OS === 'web' && typeof window !== 'undefined'
      ? window.location.pathname
      : '/auth/login';
    api.post('/auth/logout-banner-telemetry', {
      event,
      source: 'login_screen',
      route_path: routePath,
      redirect_target: '/auth/login?logout=1',
      expected_logout_banner: true,
    }, { silentLoading: true }).catch(() => {});
  }, []);

  const handleAuthError = useCallback((err: any, fallback: string) => {
    const detail = err?.response?.data?.detail && typeof err?.response?.data?.detail === 'object'
      ? err.response.data.detail
      : null;
    const resolvedMessage = err?.displayMessage || detail?.display_message || err?.message || fallback;
    const resolvedSteps = Array.isArray(err?.nextSteps)
      ? err.nextSteps
      : Array.isArray(detail?.next_steps)
        ? detail.next_steps
        : [];

    setError(resolvedMessage);
    const nextRecovery = {
      code: err?.code || detail?.code || '',
      blockedUntil: err?.blockedUntil || detail?.blocked_until || '',
      lockedAt: err?.lockedAt || detail?.locked_at || '',
      failedAttempts: err?.failedAttempts ?? detail?.failed_attempts,
      retryAfterSeconds: Number(err?.retryAfterSeconds || detail?.retry_after_seconds || 0),
      supportUrl: err?.supportUrl || detail?.support_url || 'mailto:security@realaicoach.app',
      resetPasswordUrl: err?.resetPasswordUrl || detail?.reset_password_url || '/auth/forgot-password',
      recoveryActions: Array.isArray(err?.recoveryActions) ? err.recoveryActions : Array.isArray(detail?.recovery_actions) ? detail.recovery_actions : [],
      nextSteps: resolvedSteps,
      displayMessage: resolvedMessage,
      emailNotificationSent: Boolean(err?.emailNotificationSent || detail?.email_notification_sent),
      idvAccessToken: err?.idvAccessToken || detail?.idv_access_token || '',
    };
    setAuthRecovery(nextRecovery);
    setRecoveryCountdown(nextRecovery.retryAfterSeconds || 0);
  }, []);

  useEffect(() => {
    if (!recoveryCountdown || recoveryCountdown <= 0) return;
    const timer = setTimeout(() => setRecoveryCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => clearTimeout(timer);
  }, [recoveryCountdown]);

  const lockoutHelpText = useMemo(() => {
    if (!authRecovery?.code) return '';
    if (authRecovery.code === 'login_rate_limited' && recoveryCountdown > 0) {
      return `Try again in about ${recoveryCountdown}s.`;
    }
    if (authRecovery.code === 'ip_temporarily_blocked' && authRecovery.blockedUntil) {
      try {
        return `Temporary network lock until ${new Date(authRecovery.blockedUntil).toLocaleTimeString()}.`;
      } catch {
        return 'Temporary network lock is active.';
      }
    }
    if (authRecovery.code === 'otp_account_locked') {
      return tx('login.recovery.unlockHelp', 'Use Forgot Password to securely unlock your account, or contact support if you need immediate help.');
    }
    if (String(authRecovery.code || '').startsWith('risk_engine_') && authRecovery.displayMessage) {
      return authRecovery.displayMessage;
    }
    return '';
  }, [authRecovery, recoveryCountdown]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setLogoutRedirectHold(false);
      return;
    }

    const logoutFlag = Array.isArray(logoutParam) ? logoutParam[0] : logoutParam;
    if (logoutFlag !== '1') {
      logoutBannerTelemetryTrackedRef.current = false;
      setLogoutRedirectHold(false);
      return;
    }

    logoutBannerTelemetryTrackedRef.current = false;
    setPostLogoutBanner(true);
    setLogoutRedirectHold(true);

    let timer: ReturnType<typeof setTimeout> | null = null;

    try {
      const currentUrl = new URL(window.location.href);
      if (currentUrl.searchParams.get('logout') === '1') {
        currentUrl.searchParams.delete('logout');
        const nextQuery = currentUrl.searchParams.toString();
        const nextUrl = `${currentUrl.pathname}${nextQuery ? `?${nextQuery}` : ''}${currentUrl.hash || ''}`;
        window.history.replaceState({}, '', nextUrl);
        timer = setTimeout(() => setLogoutRedirectHold(false), 1200);
      }
    } catch {
      setLogoutRedirectHold(false);
    }

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [logoutParam]);

  useEffect(() => {
    if (!postLogoutBanner || logoutBannerTelemetryTrackedRef.current) return;
    logoutBannerTelemetryTrackedRef.current = true;
    emitLogoutBannerTelemetry('shown');
  }, [postLogoutBanner, emitLogoutBannerTelemetry]);

  const formattedRecoveryCountdown = useMemo(() => {
    if (!recoveryCountdown || recoveryCountdown <= 0) return '';
    const minutes = Math.floor(recoveryCountdown / 60);
    const seconds = recoveryCountdown % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }, [recoveryCountdown]);
  const [localLoading, setLocalLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [focusedField, setFocusedField] = useState('');
  const [lastUsedMethod, setLastUsedMethod] = useState<string | null>(null);

  // QR Quick Login state
  const [showQR, setShowQR] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [qrStatus, setQrStatus] = useState<'idle' | 'generating' | 'pending' | 'approved' | 'expired' | 'error'>('idle');
  const qrPollRef = useRef<any>(null);
  const redirectingRef = useRef(false);

  const resolvedReturnTo = useMemo(() => {
    const raw = Array.isArray(returnToParam) ? returnToParam[0] : returnToParam;
    if (!raw || typeof raw !== 'string') return '';
    try {
      const decoded = decodeURIComponent(raw).trim();
      return decoded;
    } catch {
      return raw.trim();
    }
  }, [returnToParam]);

  // SSO Diagnostics state
  const [ssoDiagnostics, setSsoDiagnostics] = useState<'idle' | 'waiting' | 'fallback'>('idle');
  const [ssoProvider, setSsoProvider] = useState<string>('');
  const ssoDiagTimerRef = useRef<any>(null);
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [magicLinkLoading, setMagicLinkLoading] = useState(false);
  const [magicLinkEmail, setMagicLinkEmail] = useState('');
  const [ssoCallbacks, setSsoCallbacks] = useState<{ microsoft?: string; apple?: string } | null>(null);

  // Detect iframe mode (App Preview) — deferred to useEffect to prevent hydration mismatch.
  // React Error #418 occurs if server-rendered HTML differs from client hydration.
  // Static HTML renders with isIframe=false; if we set it to true during hydration, React crashes.
  // By using useState + useEffect, the initial render matches the static HTML (false),
  // then updates to true after mount — avoiding the mismatch entirely.
  const [isInIframe, setIsInIframe] = useState(false);
  const [isInCrossOriginIframe, setIsInCrossOriginIframe] = useState(false);
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    let inIframe = false;
    try {
      inIframe = window.self !== window.top;
    } catch {
      inIframe = true;
    }
    setIsInIframe(inIframe);
    if (!inIframe) {
      setIsInCrossOriginIframe(false);
      return;
    }
    try { void window.top?.location?.href; } catch { setIsInCrossOriginIframe(true); }
  }, []);

  // If this page was opened as a popup by an iframe, relay the SSO token back and close.
  // NOTE: Google SSO (session_id) is NOT relayed here — AuthContext.tsx handles exchanging
  // session_id for a real session_token via API before relaying. Only relay MS/Apple tokens
  // which are already valid session tokens.
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !window.opener) return;
    const query = new URLSearchParams(window.location.search || '');
    const ssoStatus = query.get('sso_status');
    const ssoProvider = query.get('sso_provider');
    if (ssoStatus === 'success' && ssoProvider) {
      try {
        const targetOrigin = resolveSsoPopupTargetOrigin();
        if (!targetOrigin) return;
        window.opener.postMessage({ type: 'sso_complete', provider: ssoProvider }, targetOrigin);
      } catch (e) {
        console.error('postMessage completion to opener failed:', e);
      }
      setTimeout(() => { try { window.close(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 400);
    } else if (window.location.hash.includes('ms_session_token=') || window.location.hash.includes('apple_session_token=')) {
      setError(tx('login.errors.failedTryAgain', 'Secure SSO callback failed. Please try again.'));
    }
  }, []);

  const logSsoTelemetry = useCallback((provider: string, phase: string, extra: Record<string, any> = {}) => {
    if (Platform.OS !== 'web') return;
    api.post('/auth/sso-telemetry', {
      provider: provider.toLowerCase(),
      phase,
      iframe_mode: isInIframe,
      cross_origin_iframe: isInCrossOriginIframe,
      context: 'login',
      ...extra,
    }).catch(() => {});
  }, [isInIframe, isInCrossOriginIframe]);

  const redirectToApp = useCallback((lastRoute?: string, platformRole?: string | null) => {
    if (redirectingRef.current) return;
    redirectingRef.current = true;
    setShowSuccess(true);
    setTimeout(() => {
      const normalizeCandidate = (route?: string) => {
        if (!route) return '';
        const trimmed = normalizeIncomingSystemPath(route.trim());
        if (!trimmed) return '';
        if (!trimmed.startsWith('/')) return '';
        if (trimmed === '/dashboard') return '/';
        return trimmed;
      };

      const preferredCandidate = normalizeCandidate(lastRoute) || normalizeCandidate(resolvedReturnTo);
      const isValidRoute = preferredCandidate && preferredCandidate !== '/auth/login' && hasKnownTopLevelSegment(preferredCandidate);

      if (isValidRoute) {
        router.replace(preferredCandidate as any);
      } else {
        // Role-aware landing — platform employees land on their tailored view.
        // Falls back to auth-context user's role when caller didn't pass one.
        const role = platformRole ?? (user as any)?.platform_role ?? null;
        if (role) {
          router.replace(getLandingRouteForRole(role) as any);
        } else {
          router.replace('/');
        }
      }
    }, 800);
  }, [resolvedReturnTo, router, user]);

  // Listen for SSO tokens from popup windows (when running inside iframe)
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!isInIframe) return;
    const handler = async (event: MessageEvent) => {
      if (!isTrustedSsoMessageOrigin(event.origin)) return;
      if (!event.data) return;
      if (event.data.type === 'sso_complete') {
        cancelSsoDiagnostics();
        const provider = String(event.data.provider || 'unknown');
        try {
          logSsoTelemetry(provider, 'callback_received', { popup_method: 'cookie_only_complete' });
          setCachedToken(null);
          await refreshUser();
          redirectToApp();
        } catch (err) {
          logSsoTelemetry(provider, 'callback_error', { note: 'cookie-only completion failed' });
          setError(tx('login.errors.failedTryAgain', 'Login failed. Please try again.'));
        }
        return;
      }
      if (event.data.type !== 'sso_token' || !event.data.token) return;
      cancelSsoDiagnostics();
      const token = event.data.token;
      const provider = String(event.data.provider || 'unknown');
      try {
        logSsoTelemetry(provider, 'callback_received', { popup_method: 'postmessage' });
        setCachedToken(null);
        try { await AsyncStorage.setItem('last_login_method', event.data.provider || 'sso'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        try { localStorage.setItem('last_login_method', event.data.provider || 'sso'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        await refreshUser();
        redirectToApp();
      } catch (err) {
        logSsoTelemetry(provider, 'callback_error', { note: 'postmessage token processing failed' });
        console.error('SSO popup token processing error:', err);
        setError(tx('login.errors.failedTryAgain', 'Login failed. Please try again.'));
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [cancelSsoDiagnostics, isInIframe, logSsoTelemetry, refreshUser, redirectToApp, setError, tx]);

  // Save last used login method
  const saveLastMethod = async (method: string) => {
    setLastUsedMethod(method);
    try {
      await AsyncStorage.setItem('last_login_method', method);
    } catch (err) {
      console.warn('Failed to save last login method:', err);
    }
  };

  // Restore last login method on mount
  useEffect(() => {
    AsyncStorage.getItem('last_login_method').then(method => {
      if (!method) return;
      setLastUsedMethod(method);
      if (method === 'otp') setLoginMethod('otp');
      else if (method === 'pin') setAltMode('pin');
      else if (method === 'passkey') setAltMode('passkey');
    }).catch(() => {});
  }, []);

  const isBusy = loading || localLoading || otpLoginLoading;
  const pwStrength = getStrength(password, T);

  // Auto-redirect when user is authenticated (e.g. after MS SSO callback sets user in AuthContext)
  useEffect(() => {
    if (user && !showSuccess && !show2FA && !logoutRedirectHold) {
      redirectToApp();
    }
  }, [user, showSuccess, show2FA, logoutRedirectHold, redirectToApp]);

  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideUp, { toValue: 0, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [fadeIn, slideUp]);

  // Handle Magic Link token from URL hash (#magic_token=...)
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const hash = window.location.hash;
    if (!hash.includes('magic_token=')) return;
    const token = hash.split('magic_token=')[1]?.split('&')[0];
    if (!token) return;
    window.history.replaceState(null, '', window.location.pathname + window.location.search);
    (async () => {
      try {
        const res = await api.get(`/auth/magic-link/verify?token=${encodeURIComponent(token)}`);
        if (res.data?.session_token) {
          await AsyncStorage.setItem('session_token', res.data.session_token);
          setCachedToken(res.data.session_token);
        }
        try { if (res.data?.session_token) localStorage.setItem('session_token', res.data.session_token); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        try { await AsyncStorage.setItem('last_login_method', 'magic_link'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        try { localStorage.setItem('last_login_method', 'magic_link'); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginControllerLegacy.ts#catch9', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        if (!res.data?.session_token) setCachedToken(null);
        await refreshUser();
        redirectToApp();
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Magic link expired or invalid. Please request a new one.');
      }
    })();
  }, [refreshUser, redirectToApp]);

  // SSO Diagnostics: start timer when SSO button clicked, show fallback after timeout
  const startSsoDiagnostics = (provider: string) => {
    setSsoProvider(provider);
    setSsoDiagnostics('waiting');
    setMagicLinkEmail(email || '');
    if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
    ssoDiagTimerRef.current = setTimeout(() => {
      setSsoDiagnostics('fallback');
    }, 8000);
  };

  // Cancel SSO diagnostics when login succeeds
  useEffect(() => {
    if (user || showSuccess) {
      if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
      setSsoDiagnostics('idle');
    }
  }, [user, showSuccess]);

  // Cleanup SSO diagnostics timer
  useEffect(() => {
    return () => { if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current); };
  }, []);

  // Also cancel diagnostics when postMessage token received
  const cancelSsoDiagnostics = () => {
    if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
    setSsoDiagnostics('idle');
  };

  // Send magic link
  const handleSendMagicLink = async () => {
    if (!magicLinkEmail) { setError(tx('login.magicLink.enterEmailFirst', 'Please enter your email first')); return; }
    setMagicLinkLoading(true);
    setError('');
    try {
      await api.post('/auth/magic-link/send', { email: magicLinkEmail });
      setMagicLinkSent(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to send magic link');
    } finally {
      setMagicLinkLoading(false);
    }
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || !ssoErrorCode || (ssoErrorCode !== 'invalid_request' && ssoErrorCode !== 'token_failed')) return;
    api.get('/auth/sso-config', { silentLoading: true }).then((res) => {
      setSsoCallbacks({
        microsoft: res.data?.microsoft_callback,
        apple: res.data?.apple_callback,
      });
    }).catch(() => {});
  }, [ssoErrorCode]);

  /* ─── Auth Handlers (preserved) ─── */
  const handleLogin = async () => {
    let effectiveEmail = email.trim();
    let effectivePassword = password;

    if ((!effectiveEmail || !effectivePassword) && Platform.OS === 'web') {
      const domEmail = getWebInputValue('login-email-input', 'you@example.com');
      const domPassword = getWebInputValue('login-password-input', 'Enter password');
      if (!effectiveEmail && domEmail) effectiveEmail = domEmail;
      if (!effectivePassword && domPassword) effectivePassword = domPassword;
      if (domEmail && domEmail !== email) setEmail(domEmail);
      if (domPassword && domPassword !== password) setPassword(domPassword);
    }

    if (!effectiveEmail || !effectivePassword) { setError(tx('login.errors.fillAllFields', 'Please fill in all fields')); return; }
    clearAuthIssue();
    setPostResetBanner(false);
    setPostLogoutBanner(false);
    setLogoutRedirectHold(false);
    setPendingAuthEmail(effectiveEmail);
    setPendingAuthPassword(effectivePassword);
    setPendingRememberMe(rememberMe);
    try {
      const result = await login(effectiveEmail, effectivePassword, rememberMe);
      if (result?.requires_2fa) {
        setPending2FAUserId(result.user_id);
        const codeReused = Boolean(result?.code_reused);
        setOtpHint(
          codeReused
            ? tx('login.otp.codeStillValid', 'Your existing verification code is still valid. Check your email inbox.')
            : tx('login.otp.newCodeSent', 'A new verification code has been sent to your email inbox.')
        );
        setOtpCode('');
        setShow2FA(true);
        if (Array.isArray(result?.next_steps) && result.next_steps.length > 0) {
          setAuthRecovery({
            code: result?.risk_code || 'risk_engine_step_up_mfa',
            blockedUntil: '',
            lockedAt: '',
            failedAttempts: 0,
            retryAfterSeconds: 0,
            supportUrl: result?.support_url || 'mailto:security@realaicoach.app',
            resetPasswordUrl: '/auth/forgot-password',
            recoveryActions: [],
            nextSteps: result.next_steps,
            displayMessage: result?.display_message || tx('login.security.stepUpRequired', 'Additional verification is required to protect your account.'),
            emailNotificationSent: Boolean(result?.email_notification_sent),
            idvAccessToken: result?.idv_access_token || '',
          });
          setError(result?.display_message || tx('login.security.stepUpRequired', 'Additional verification is required to protect your account.'));
        } else {
          setError('');
        }
        return;
      }
      await saveLastMethod('password');
      
      // Check if user should be prompted to enroll passkey
      const shouldPrompt = await shouldShowPasskeyEnrollmentPrompt(effectiveEmail);
      if (shouldPrompt) {
        setShowPasskeyEnrollmentPrompt(true);
        setPasskeyPromptPendingRoute(result?.last_active_route || '/(tabs)');
        return; // Don't redirect yet, show prompt first
      }
      
      redirectToApp(result?.last_active_route);
    } catch (err: any) { handleAuthError(err, tx('login.errors.failed', 'Login failed')); }
  };

  const handleRequestOtp = async () => {
    if (!email) { setError(tx('login.otp.emailRequired', 'Email is required for OTP login')); return; }
    try {
      clearAuthIssue(); setOtpLoginLoading(true);
      const response = await requestOtp(email, otpLoginRequested);
      const codeReused = Boolean(response?.code_reused);
      if (codeReused) {
        setOtpLoginHint(tx('login.otp.codeStillValid', 'Your existing verification code is still valid. Check your email inbox.'));
      } else if (otpLoginRequested) {
        setOtpLoginHint(tx('login.otp.newCodeSent', 'A new verification code has been sent to your email inbox.'));
      } else {
        setOtpLoginHint(response?.otp_hint || tx('login.otp.checkEmailCode', 'Check your email for the 8-digit code.'));
      }
      setOtpLoginRequested(true); setOtpLoginCode('');
    } catch (err: any) { handleAuthError(err, 'Failed to request code'); }
    finally { setOtpLoginLoading(false); }
  };

  const handleOtpLogin = async () => {
    if (!email || !otpLoginCode) { setError(tx('login.otp.emailCodeRequired', 'Email and code are required')); return; }
    if (otpLoginCode.replace(/\D/g, '').length !== 8) { setError(tx('login.otp.enterEightDigits', 'Please enter the 8-digit code')); return; }
    try { clearAuthIssue(); await loginWithOtp(email, otpLoginCode); await saveLastMethod('otp'); redirectToApp(); }
    catch (err: any) { handleAuthError(err, tx('login.otp.failed', 'OTP login failed')); }
  };

  const handleResendOTP = async () => {
    if (resending) return;
    const resendEmail = pendingAuthEmail || email.trim();
    const resendPassword = pendingAuthPassword || password;
    if (!resendEmail || !resendPassword) {
      setError(tx('login.otp.resendNeedsCredentials', 'Please sign in again to request a fresh verification code.'));
      return;
    }
    setResending(true); setError('');
    try {
      const result = await login(resendEmail, resendPassword, pendingRememberMe, true);
      if (result?.requires_2fa) {
        const codeReused = Boolean(result?.code_reused);
        setOtpHint(
          codeReused
            ? tx('login.otp.codeStillValid', 'Your existing verification code is still valid. Check your email inbox.')
            : tx('login.otp.newCodeSent', 'A new verification code has been sent to your email inbox.')
        );
        setOtpCode('');
        return;
      }
      await saveLastMethod('password');
      redirectToApp(result?.last_active_route);
    } catch (err: any) {
      handleAuthError(err, tx('login.otp.verificationFailed', 'Verification failed'));
    } finally {
      setResending(false);
    }
  };

  const handle2FAVerify = async () => {
    if (otpCode.replace(/\D/g, '').length !== 8) { setError(tx('login.otp.enterEightDigits', 'Please enter the 8-digit code')); return; }
    clearAuthIssue();
    try {
      const result = await verify2FA(pending2FAUserId, otpCode, pendingRememberMe);
      setShow2FA(false);
      setPendingAuthPassword('');
      await saveLastMethod('password');
      redirectToApp(result?.last_active_route);
    }
    catch (err: any) { handleAuthError(err, tx('login.otp.verificationFailed', 'Verification failed')); }
  };

  const handlePinLogin = async () => {
    try {
      setLocalLoading(true);
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(email)}`);
      if (!lookup.data?.exists || !lookup.data?.user_id) { Alert.alert('Not Registered', 'Please, Sign Up / Register First.'); return; }
      const res = await api.post('/auth/biometric/verify-pin', { user_id: lookup.data.user_id, pin });
      if (res.data?.session_token) {
        await AsyncStorage.setItem('session_token', res.data.session_token);
        setCachedToken(res.data.session_token);
      } else {
        setCachedToken(null);
      }
      if (res.status === 200) {
        await refreshUser(); await saveLastMethod('pin'); redirectToApp();
      } else { Alert.alert('Login failed', 'Invalid PIN'); }
    } catch (e: any) { Alert.alert('Login failed', e?.response?.data?.detail || 'Invalid PIN'); }
    finally { setLocalLoading(false); }
  };

  const handlePasskeyLogin = async () => {
    if (!(Platform.OS === 'web' && typeof window !== 'undefined' && (window as any).PublicKeyCredential)) {
      Alert.alert('Unavailable', 'Passkey login is currently supported on web browsers.'); return;
    }
    try {
      setLocalLoading(true);
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(email)}`);
      if (!lookup.data?.exists || !lookup.data?.user_id) { Alert.alert('Not Registered', 'Please, Sign Up / Register First.'); return; }
      const userId = lookup.data.user_id;
      const optRes = await api.post('/auth/biometric/webauthn-auth-options', { user_id: userId });
      const opts = optRes.data;
      const challengeBuffer = Uint8Array.from(atob(opts.challenge.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
      const allowId = opts.allowCredentials?.[0]?.id;
      const credIdBuffer = Uint8Array.from(atob(allowId.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
      const assertion = await (navigator as any).credentials.get({
        publicKey: { challenge: challengeBuffer, allowCredentials: [{ id: credIdBuffer, type: 'public-key' }], userVerification: 'required', timeout: opts.timeout }
      }) as any;
      if (!assertion) { Alert.alert('Cancelled', 'Passkey login cancelled.'); return; }
      
      // Serialize the full WebAuthn credential payload
      const serializedCredential = serializeWebAuthnCredential(assertion);
      const credId = serializedCredential.rawId;
      
      const res = await api.post('/auth/biometric/webauthn-auth-complete', { 
        user_id: userId, 
        credential_id: credId,
        credential: serializedCredential,
        challenge_id: opts.challenge_id || undefined
      });
      if (res.data?.session_token) {
        await AsyncStorage.setItem('session_token', res.data.session_token);
        setCachedToken(res.data.session_token);
      }
      if (!res.data?.session_token) setCachedToken(null);
      await refreshUser(); await saveLastMethod('passkey'); redirectToApp();
    } catch (e: any) { if (e?.name === 'NotAllowedError') return; Alert.alert('Passkey login failed', e?.response?.data?.detail || 'Unable to login with passkey'); }
    finally { setLocalLoading(false); }
  };

  // Check if user has passkey enrolled
  const checkUserPasskeyEnrollment = async (userEmail: string) => {
    if (!userEmail.trim()) return;
    try {
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(userEmail)}`);
      if (!lookup.data?.exists || !lookup.data?.user_id) {
        setUserHasPasskey(false);
        return;
      }
      const userId = lookup.data.user_id;
      const res = await api.get(`/auth/biometric/has-passkey?user_id=${userId}`, { silentLoading: true });
      setUserHasPasskey(res.data?.has_passkey || false);
    } catch (e) {
      setUserHasPasskey(false);
    }
  };

  // Check if should show passkey enrollment prompt after login
  const shouldShowPasskeyEnrollmentPrompt = async (userEmail: string): Promise<boolean> => {
    // Check if browser supports WebAuthn
    if (!(Platform.OS === 'web' && typeof window !== 'undefined' && (window as any).PublicKeyCredential)) {
      return false;
    }
    
    // Check if user has already enrolled passkey
    if (userHasPasskey === true) {
      return false;
    }
    
    // Check if user has dismissed prompt recently (don't nag every login)
    try {
      const dismissedAt = await AsyncStorage.getItem('passkey_prompt_dismissed_at');
      if (dismissedAt) {
        const dismissedDate = new Date(dismissedAt);
        const daysSinceDismissed = (Date.now() - dismissedDate.getTime()) / (1000 * 60 * 60 * 24);
        if (daysSinceDismissed < 7) {
          return false; // Don't show again for 7 days
        }
      }
    } catch (e) {}
    
    return true;
  };

  // Handle "Yes" on enrollment prompt - actually enroll the passkey
  const handlePasskeyPromptEnable = async () => {
    if (passkeyPromptBusy) return;
    setPasskeyPromptBusy(true);
    
    try {
      // Step 1: Get registration options from backend
      const optRes = await api.post('/auth/biometric/webauthn-register-options', {});
      const opts = optRes.data;
      
      // Step 2: Convert challenge to buffer
      const challengeBuffer = Uint8Array.from(
        atob(opts.challenge.replace(/-/g, '+').replace(/_/g, '/')), 
        c => c.charCodeAt(0)
      );
      
      const userIdBuffer = Uint8Array.from(
        atob(opts.user.id.replace(/-/g, '+').replace(/_/g, '/')), 
        c => c.charCodeAt(0)
      );
      
      // Step 3: Trigger browser biometric enrollment
      const credential = await (navigator as any).credentials.create({
        publicKey: {
          challenge: challengeBuffer,
          rp: opts.rp,
          user: {
            id: userIdBuffer,
            name: opts.user.name,
            displayName: opts.user.displayName,
          },
          pubKeyCredParams: opts.pubKeyCredParams,
          timeout: opts.timeout,
          attestation: opts.attestation,
          authenticatorSelection: {
            userVerification: 'required',
            residentKey: 'preferred',
          },
        }
      });
      
      if (!credential) {
        Alert.alert('Cancelled', 'Passkey enrollment was cancelled.');
        setPasskeyPromptBusy(false);
        return;
      }
      
      // Step 4: Serialize and send to backend
      const serializedCredential = serializeWebAuthnCredential(credential);
      await api.post('/auth/biometric/webauthn-register-complete', {
        credential: serializedCredential,
        challenge_id: opts.challenge_id,
        nickname: 'This device',
      });
      
      Alert.alert('Success!', 'Passkey enrolled successfully. You can now login with your fingerprint.');
      setUserHasPasskey(true);
      setShowPasskeyEnrollmentPrompt(false);
      
      // Redirect to app
      const route = passkeyPromptPendingRoute || '/(tabs)';
      redirectToApp(route);
      
    } catch (e: any) {
      if (e?.name === 'NotAllowedError') {
        // User cancelled
        setPasskeyPromptBusy(false);
        return;
      }
      Alert.alert('Enrollment failed', e?.response?.data?.detail || 'Unable to enroll passkey');
      setPasskeyPromptBusy(false);
    }
  };

  // Handle "No" on enrollment prompt
  const handlePasskeyPromptDismiss = async () => {
    if (passkeyPromptBusy) return;
    
    // Save dismissal timestamp (don't show again for 7 days)
    try {
      await AsyncStorage.setItem('passkey_prompt_dismissed_at', new Date().toISOString());
    } catch (e) {}
    
    setShowPasskeyEnrollmentPrompt(false);
    const route = passkeyPromptPendingRoute || '/(tabs)';
    redirectToApp(route);
  };

  // Check passkey enrollment status when email changes
  useEffect(() => {
    if (email && email.includes('@')) {
      checkUserPasskeyEnrollment(email);
    }
  }, [email]);

  // ── Triple-Layer SSO Popup Failsafe (iframe-safe) ──
  // Layer 1: window.open() — direct user-click context, works in most iframes
  // Layer 2: dynamic <a> element click — bypasses popup blockers entirely
  // Layer 3: diagnostics panel with direct link + magic link fallback
  const openSsoPopup = (url: string, windowName: string, provider: string) => {
    startSsoDiagnostics(provider);
    logSsoTelemetry(provider, 'popup_attempt');

    // Layer 1: Try window.open() (most reliable in user-click context)
    try {
      const popup = window.open(url, windowName, 'width=500,height=700,left=200,top=100');
      if (popup && !popup.closed) {
        logSsoTelemetry(provider, 'popup_opened', { popup_method: 'window_open' });
        clientLogger.log(`[SSO] ${provider} popup opened via window.open()`);
        return; // Success — diagnostics timer handles the rest
      }
    } catch (e) {
      console.warn(`[SSO] window.open() failed for ${provider}:`, e);
    }

    // Layer 2: Dynamic anchor element — browsers never block user-initiated <a> clicks
    clientLogger.log(`[SSO] Trying dynamic anchor fallback for ${provider}`);
    try {
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.target = windowName;
      anchor.rel = 'opener';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      logSsoTelemetry(provider, 'popup_opened', { popup_method: 'dynamic_anchor' });
      clientLogger.log(`[SSO] ${provider} popup opened via dynamic anchor`);
      return;
    } catch (e) {
      console.warn(`[SSO] Dynamic anchor failed for ${provider}:`, e);
    }

    // Layer 3: If both failed, immediately show fallback UI
    logSsoTelemetry(provider, 'popup_failed', { note: 'window_open and dynamic_anchor failed' });
    clientLogger.log(`[SSO] All popup methods failed for ${provider}, showing fallback`);
    setSsoDiagnostics('fallback');
  };

  const openSsoFullWindow = (url: string, provider: string) => {
    logSsoTelemetry(provider, 'direct_redirect', { popup_method: 'full_window' });
    try {
      if (isInIframe || isInCrossOriginIframe) {
        const popup = window.open(url, '_blank', 'noopener,noreferrer');
        if (popup && !popup.closed) {
          return;
        }
      }
      (window.top || window).location.href = url;
    } catch {
      window.location.href = url;
    }
  };

  const handleGoogleLogin = async () => {
    try {
      await saveLastMethod('google');
      logSsoTelemetry('google', 'click');
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const url = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(webOrigin + '/')}`;
        if (isInIframe) {
          openSsoPopup(url, 'sso_google_popup', 'Google');
        } else {
          logSsoTelemetry('google', 'direct_redirect', { popup_method: 'top_navigation' });
          (window.top || window).location.href = url;
        }
      } else {
        await loginWithGoogle();
      }
    } catch { Alert.alert('Error', 'Google login failed'); }
  };

  // ── QR Quick Login Handlers ──
  const generateQR = async () => {
    setQrStatus('generating');
    setQrUrl('');
    setError('');
    try {
      const res = await api.post('/auth/qr/generate');
      const qrPayload = normalizeAuthQrPayload(res.data?.qr_url);
      if (!isValidAuthQrPayload(qrPayload)) {
        throw new Error('Invalid QR approval payload');
      }
      setQrUrl(qrPayload);
      setQrStatus('pending');
      // Start polling for approval
      if (qrPollRef.current) clearInterval(qrPollRef.current);
      qrPollRef.current = setInterval(async () => {
        try {
          const statusRes = await api.get(`/auth/qr/status/${res.data.session_id}`);
          if (statusRes.data.status === 'approved' && statusRes.data.session_token) {
            clearInterval(qrPollRef.current);
            qrPollRef.current = null;
            // Auto-login with the received token
            await AsyncStorage.setItem('session_token', statusRes.data.session_token);
            setCachedToken(statusRes.data.session_token);
            await refreshUser();
            await saveLastMethod('qr');
            redirectToApp();
          } else if (statusRes.data.status === 'expired') {
            clearInterval(qrPollRef.current);
            qrPollRef.current = null;
            setQrStatus('expired');
          }
        } catch { /* ignore poll errors */ }
      }, 2000);
    } catch (e: any) {
      setQrStatus('error');
      setError(e?.response?.data?.detail || 'Failed to generate QR code');
    }
  };

  // Cleanup QR polling on unmount
  useEffect(() => {
    return () => { if (qrPollRef.current) clearInterval(qrPollRef.current); };
  }, []);

  // SSO handlers use window.top.location.href with absolute URLs for iframe-safe navigation

  const handleMicrosoftLogin = () => {
    saveLastMethod('microsoft');
    logSsoTelemetry('microsoft', 'click');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const url = `${liveApiBase}/api/auth/microsoft/login`;
      if (isInIframe || isMobile) {
        openSsoFullWindow(url, 'microsoft');
      } else {
        logSsoTelemetry('microsoft', 'direct_redirect', { popup_method: 'top_navigation' });
        (window.top || window).location.href = url;
      }
    } else {
      loginWithMicrosoft();
    }
  };

  const handleAppleLogin = () => {
    saveLastMethod('apple');
    logSsoTelemetry('apple', 'click');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const url = `${liveApiBase}/api/auth/apple/login`;
      if (isInIframe || isMobile) {
        openSsoFullWindow(url, 'apple');
      } else {
        logSsoTelemetry('apple', 'direct_redirect', { popup_method: 'top_navigation' });
        (window.top || window).location.href = url;
      }
    }
  };


  return {
    router, loading, colors, darkMode, T, s, webAssetBase, isDesktop, isTablet, isMobile, isCompactMobile, isUltraCompact, webOrigin, liveApiBase, tx, headingText, subheadingText, SSO_ERROR_MESSAGES, email, setEmail, password, setPassword, showPassword, setShowPassword, error, setError, authRecovery, ssoErrorCode, setSsoErrorCode, show2FA, setShow2FA, otpCode, setOtpCode, setPendingAuthPassword, otpHint, loginMethod, setLoginMethod, otpLoginCode, setOtpLoginCode, otpLoginHint, otpLoginRequested, otpLoginLoading, resending, rememberMe, setRememberMe, altMode, setAltMode, pin, setPin, postLogoutBanner, setPostLogoutBanner, postResetBanner, setPostResetBanner, emitLogoutBannerTelemetry, lockoutHelpText, formattedRecoveryCountdown, localLoading, showSuccess, focusedField, setFocusedField, lastUsedMethod, ssoCallbacks, showQR, setShowQR, qrUrl, qrStatus, ssoDiagnostics, ssoProvider, magicLinkSent, setMagicLinkSent, magicLinkLoading, setMagicLinkLoading, magicLinkEmail, setMagicLinkEmail, isInIframe, isInCrossOriginIframe, logSsoTelemetry, redirectToApp, isBusy, pwStrength, fadeIn, slideUp, startSsoDiagnostics, cancelSsoDiagnostics, handleSendMagicLink, handleLogin, handleRequestOtp, handleOtpLogin, handleResendOTP, handle2FAVerify, handlePinLogin, handlePasskeyLogin, openSsoFullWindow, handleGoogleLogin, generateQR, handleMicrosoftLogin, handleAppleLogin, userHasPasskey, setUserHasPasskey, checkUserPasskeyEnrollment, showPasskeyEnrollmentPrompt, passkeyPromptBusy, handlePasskeyPromptDismiss, handlePasskeyPromptEnable, setThemeMode
  };
}
