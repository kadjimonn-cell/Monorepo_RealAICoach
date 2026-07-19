import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Platform, useWindowDimensions } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api from '../../../services/api';
import { useAuth } from '../../../context/AuthContext';
import { useTheme } from '../../../context/ThemeContext';
import { useTranslation } from '../../../hooks/useTranslation';
import { getLandingRouteForRole } from '../../../lib/platformRoleLanding';
import { hasKnownTopLevelSegment, normalizeIncomingSystemPath } from '../../../utils/routeResolution';
import { resolveRuntimeBaseUrl } from '../../../utils/runtimeBaseUrl';
import { getStrength } from './passwordStrength';
import { makeStyles } from './loginStyles';
import { useLoginRecovery } from './useLoginRecovery';
import { useLoginOtp } from './useLoginOtp';
import { useLoginSso } from './useLoginSso';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';

const ENABLE_P0_LOGIN_BANNER_CONTRACT = String(process.env.REACT_APP_ENABLE_AUTH_BANNER_P0_CONTRACT || 'true').toLowerCase() === 'true';

export function useLoginController(forceCompactMode = false) {
  const router = useRouter();
  const { reset, logout: logoutParam, return_to: returnToParam } = useLocalSearchParams<{ reset?: string | string[]; logout?: string | string[]; return_to?: string | string[] }>();
  const { user, login, verify2FA, loginWithGoogle, loginWithMicrosoft, loginWithApple, requestOtp, loginWithOtp, loading, refreshUser } = useAuth();
  const { t } = useTranslation();
  const { width } = useWindowDimensions();
  const { darkMode, colors, setThemeMode } = useTheme();

  const T = {
    bg: colors.bg,
    bgAlt: colors.bgAlt,
    bgCard: colors.card,
    text: colors.text,
    text2: colors.textSec,
    text3: colors.textMuted,
    gray300: colors.textSec,
    gray400: colors.textMuted,
    cyan: colors.accent,
    neonBlue: colors.primary,
    teal: colors.accent,
    purple: colors.purple,
    success: colors.success,
    error: colors.error,
    warning: colors.warning,
    errorText: colors.errorText,
    successText: colors.successText,
    infoText: colors.infoText,
    warningText: (colors as any).warningText || colors.warning,
    purpleText: (colors as any).purpleText || colors.purple,
    glassBorder: colors.glassBorder,
    glassSurface: colors.glassSurface,
    glassHL: colors.hover,
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
  const [rememberMe, setRememberMe] = useState(false);
  const [altMode, setAltMode] = useState<'none' | 'pin' | 'passkey'>('none');
  const [pin, setPin] = useState('');
  const [userHasPasskey, setUserHasPasskey] = useState<boolean | null>(null);
  const [localLoading, setLocalLoading] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [focusedField, setFocusedField] = useState('');
  const [lastUsedMethod, setLastUsedMethod] = useState<string | null>(null);
  const [showPasskeyEnrollmentPrompt, setShowPasskeyEnrollmentPrompt] = useState(false);
  const [passkeyPromptPendingRoute, setPasskeyPromptPendingRoute] = useState('');
  const [passkeyPromptBusy, setPasskeyPromptBusy] = useState(false);

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

  const initialError = useMemo(() => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        const ssoErr = urlParams.get('sso_error');
        if (ssoErr && SSO_ERROR_MESSAGES[ssoErr]) return SSO_ERROR_MESSAGES[ssoErr];
        if (ssoErr) return tx('login.errors.failedTryAgain', 'Login failed. Please try again.');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginController.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return '';
  }, [SSO_ERROR_MESSAGES, tx]);

  const recovery = useLoginRecovery({
    initialError,
    tx,
  });

  const getInitialLogoutLanding = (): boolean => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        return new URLSearchParams(window.location.search).get('logout') === '1';
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginController.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return false;
  };

  const [postResetBanner, setPostResetBanner] = useState(Array.isArray(reset) ? reset[0] === 'success' : reset === 'success');
  const [postLogoutBanner, setPostLogoutBanner] = useState(getInitialLogoutLanding);
  const [postRedirectedBanner, setPostRedirectedBanner] = useState(false);
  const [logoutRedirectHold, setLogoutRedirectHold] = useState(getInitialLogoutLanding);
  const logoutBannerTelemetryTrackedRef = useRef(false);
  const redirectingRef = useRef(false);

  const getWebInputValue = useCallback((testId: string, placeholder?: string): string => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return '';
    try {
      const byDataTestId = document.querySelector(`[data-testid="${testId}"]`) as HTMLInputElement | null;
      if (byDataTestId && typeof byDataTestId.value === 'string' && byDataTestId.value.trim()) return byDataTestId.value.trim();

      const nestedDataTestId = document.querySelector(`[data-testid="${testId}"] input`) as HTMLInputElement | null;
      if (nestedDataTestId && typeof nestedDataTestId.value === 'string' && nestedDataTestId.value.trim()) return nestedDataTestId.value.trim();

      const byTestId = document.querySelector(`[testID="${testId}"]`) as HTMLInputElement | null;
      if (byTestId && typeof byTestId.value === 'string' && byTestId.value.trim()) return byTestId.value.trim();

      if (placeholder) {
        const byPlaceholder = document.querySelector(`input[placeholder="${placeholder}"]`) as HTMLInputElement | null;
        if (byPlaceholder && typeof byPlaceholder.value === 'string' && byPlaceholder.value.trim()) return byPlaceholder.value.trim();
      }
    } catch {
      return '';
    }
    return '';
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

  const resolvedReturnTo = useMemo(() => {
    const routeParam = Array.isArray(returnToParam) ? returnToParam[0] : returnToParam;
    let raw = routeParam;
    if ((!raw || typeof raw !== 'string') && Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        const qs = new URLSearchParams(window.location.search);
        raw = qs.get('return_to') || qs.get('returnTo') || '';
      } catch {
        raw = '';
      }
    }
    if (!raw || typeof raw !== 'string') return '';
    try {
      return decodeURIComponent(raw).trim();
    } catch {
      return raw.trim();
    }
  }, [returnToParam]);

  const resolvedAuthReason = useMemo(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return '';
    try {
      const qs = new URLSearchParams(window.location.search);
      const reason = String(qs.get('auth_reason') || '').trim().toLowerCase();
      return reason;
    } catch {
      return '';
    }
  }, []);

  const redirectToApp = useCallback((lastRoute?: string, platformRole?: string | null) => {
    if (redirectingRef.current) return;
    redirectingRef.current = true;
    setShowSuccess(true);
    setTimeout(() => {
      const normalizeCandidate = (route?: string) => {
        if (!route) return '';
        const trimmed = normalizeIncomingSystemPath(route.trim());
        if (!trimmed || !trimmed.startsWith('/')) return '';
        if (trimmed === '/dashboard') return '/dashboard';
        return trimmed;
      };

      const preferredCandidate = normalizeCandidate(lastRoute) || normalizeCandidate(resolvedReturnTo);
      const isValidRoute = preferredCandidate && preferredCandidate !== '/auth/login' && hasKnownTopLevelSegment(preferredCandidate);

      if (isValidRoute) {
        router.replace(preferredCandidate as any);
        return;
      }

      const role = platformRole ?? (user as any)?.platform_role ?? null;
      if (role) {
        router.replace(getLandingRouteForRole(role) as any);
      } else {
        router.replace('/dashboard');
      }
    }, 800);
  }, [resolvedReturnTo, router, user]);

  const saveLastMethod = useCallback(async (method: string) => {
    setLastUsedMethod(method);
    try {
      await AsyncStorage.setItem('last_login_method', method);
    } catch (err) {
      console.warn('Failed to save last login method:', err);
    }
  }, []);

  const otpFlow = useLoginOtp({
    email,
    setEmail,
    password,
    setPassword,
    rememberMe,
    setPostResetBanner,
    setPostLogoutBanner,
    setLogoutRedirectHold,
    tx,
    login,
    requestOtp,
    loginWithOtp,
    verify2FA,
    clearAuthIssue: recovery.clearAuthIssue,
    handleAuthError: recovery.handleAuthError,
    setAuthRecovery: recovery.setAuthRecovery,
    setError: recovery.setError,
    redirectToApp,
    saveLastMethod,
    getWebInputValue,
    refreshUser,
    onPasswordLoginSuccess: async (result) => {
      if (Platform.OS !== 'web') return false;
      try {
        const eligibility = await api.get('/auth/biometric/enrollment-eligibility', { silentLoading: true });
        if (!eligibility?.data?.should_prompt) return false;
        setPasskeyPromptPendingRoute(result?.last_active_route || '');
        setShowPasskeyEnrollmentPrompt(true);
        return true;
      } catch {
        return false;
      }
    },
  });

  const {
    handlePinLogin: handlePinLoginFlow,
    handlePasskeyLogin: handlePasskeyLoginFlow,
    setLoginMethod,
    show2FA,
    otpLoginLoading,
  } = otpFlow;

  const ssoFlow = useLoginSso({
    email,
    tx,
    setError: recovery.setError,
    webOrigin,
    liveApiBase,
    isMobile,
    user,
    showSuccess,
    loginWithGoogle,
    loginWithMicrosoft,
    loginWithApple,
    refreshUser,
    redirectToApp,
    saveLastMethod,
  });

  const handleLogin = useCallback(async () => {
    if (localLoading) return;
    try {
      setLocalLoading(true);
      await otpFlow.handleLogin();
    } finally {
      setLocalLoading(false);
    }
  }, [localLoading, otpFlow.handleLogin]);

  const handlePinLogin = useCallback(async () => {
    try {
      setLocalLoading(true);
      await handlePinLoginFlow(pin);
    } finally {
      setLocalLoading(false);
    }
  }, [handlePinLoginFlow, pin]);

  const handlePasskeyLogin = useCallback(async () => {
    try {
      setLocalLoading(true);
      await handlePasskeyLoginFlow();
    } finally {
      setLocalLoading(false);
    }
  }, [handlePasskeyLoginFlow]);

  const handlePasskeyPromptDismiss = useCallback(async () => {
    if (passkeyPromptBusy) return;
    try {
      setPasskeyPromptBusy(true);
      setShowPasskeyEnrollmentPrompt(false);
      await api.post('/auth/biometric/enrollment-dismiss', {}, { silentLoading: true }).catch(() => {});
      redirectToApp(passkeyPromptPendingRoute || undefined);
    } finally {
      setPasskeyPromptBusy(false);
    }
  }, [passkeyPromptBusy, passkeyPromptPendingRoute, redirectToApp]);

  const handlePasskeyPromptEnable = useCallback(() => {
    if (passkeyPromptBusy) return;
    setShowPasskeyEnrollmentPrompt(false);
    const next = passkeyPromptPendingRoute ? `?prompt_passkey=1&next=${encodeURIComponent(passkeyPromptPendingRoute)}` : '?prompt_passkey=1';
    router.replace((`/security${next}`) as any);
  }, [passkeyPromptBusy, passkeyPromptPendingRoute, router]);

  const checkUserPasskeyEnrollment = useCallback(async (userEmail: string) => {
    const cleanedEmail = String(userEmail || '').trim();
    if (!cleanedEmail) {
      setUserHasPasskey(null);
      return;
    }
    try {
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(cleanedEmail)}`, { silentLoading: true });
      if (!lookup?.data?.exists || !lookup?.data?.user_id) {
        setUserHasPasskey(false);
        return;
      }
      // Use has_passkey from lookup response directly (avoids separate auth-gated call)
      if (typeof lookup.data.has_passkey === 'boolean') {
        setUserHasPasskey(lookup.data.has_passkey);
        return;
      }
      // Fallback: dedicated has-passkey endpoint
      const userId = String(lookup.data.user_id || '').trim();
      if (!userId) {
        setUserHasPasskey(false);
        return;
      }
      const res = await api.get(`/auth/biometric/has-passkey?user_id=${encodeURIComponent(userId)}`, { silentLoading: true });
      setUserHasPasskey(Boolean(res?.data?.has_passkey));
    } catch {
      setUserHasPasskey(false);
    }
  }, []);

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
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setPostRedirectedBanner(false);
      return;
    }

    const logoutFlag = Array.isArray(logoutParam) ? logoutParam[0] : logoutParam;
    if (logoutFlag === '1') {
      setPostRedirectedBanner(false);
      return;
    }

    const redirectedFromProtectedRoute = Boolean(resolvedReturnTo && resolvedReturnTo !== '/auth/login');
    if (!redirectedFromProtectedRoute) {
      setPostRedirectedBanner(false);
      return;
    }

    if (ENABLE_P0_LOGIN_BANNER_CONTRACT) {
      // P1 explicit contract: canonical-origin recovery redirects are still protected-route redirects
      // and must surface the same informative banner as unauthenticated/session_expired.
      if (resolvedAuthReason === 'origin_mismatch_recovered') {
        setPostRedirectedBanner(true);
        return;
      }

      const shouldShowBanner = (
        resolvedAuthReason === 'unauthenticated'
        || resolvedAuthReason === 'session_expired'
        || resolvedAuthReason === 'origin_mismatch_recovered'
      );
      setPostRedirectedBanner(shouldShowBanner);
      return;
    }

    setPostRedirectedBanner(redirectedFromProtectedRoute);
  }, [logoutParam, resolvedAuthReason, resolvedReturnTo]);

  useEffect(() => {
    if (!postLogoutBanner || logoutBannerTelemetryTrackedRef.current) return;
    logoutBannerTelemetryTrackedRef.current = true;
    emitLogoutBannerTelemetry('shown');
  }, [emitLogoutBannerTelemetry, postLogoutBanner]);

  useEffect(() => {
    AsyncStorage.getItem('last_login_method').then((method) => {
      if (!method) return;
      setLastUsedMethod(method);
      if (method === 'otp') setLoginMethod('otp');
      else if (method === 'pin') setAltMode('pin');
      else if (method === 'passkey') setAltMode('passkey');
    }).catch(() => {});
  }, [setLoginMethod]);

  useEffect(() => {
    if (user && !localLoading && !showSuccess && !show2FA && !logoutRedirectHold && !showPasskeyEnrollmentPrompt) {
      redirectToApp();
    }
  }, [localLoading, logoutRedirectHold, redirectToApp, show2FA, showPasskeyEnrollmentPrompt, showSuccess, user]);

  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideUp, { toValue: 0, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [fadeIn, slideUp]);

  const isBusy = localLoading || otpLoginLoading;
  const pwStrength = getStrength(password, T);

  return {
    router,
    loading,
    colors,
    darkMode,
    T,
    s,
    webAssetBase,
    isDesktop,
    isTablet,
    isMobile,
    isCompactMobile,
    isUltraCompact,
    webOrigin,
    liveApiBase,
    tx,
    headingText,
    subheadingText,
    SSO_ERROR_MESSAGES,
    email,
    setEmail,
    password,
    setPassword,
    showPassword,
    setShowPassword,
    error: recovery.error,
    setError: recovery.setError,
    authRecovery: recovery.authRecovery,
    ssoErrorCode: ssoFlow.ssoErrorCode,
    setSsoErrorCode: ssoFlow.setSsoErrorCode,
    show2FA: otpFlow.show2FA,
    setShow2FA: otpFlow.setShow2FA,
    otpCode: otpFlow.otpCode,
    setOtpCode: otpFlow.setOtpCode,
    setPendingAuthPassword: otpFlow.setPendingAuthPassword,
    otpHint: otpFlow.otpHint,
    loginMethod: otpFlow.loginMethod,
    setLoginMethod: otpFlow.setLoginMethod,
    otpLoginCode: otpFlow.otpLoginCode,
    setOtpLoginCode: otpFlow.setOtpLoginCode,
    otpLoginHint: otpFlow.otpLoginHint,
    otpLoginRequested: otpFlow.otpLoginRequested,
    otpLoginLoading: otpFlow.otpLoginLoading,
    resending: otpFlow.resending,
    rememberMe,
    setRememberMe,
    altMode,
    setAltMode,
    pin,
    setPin,
    userHasPasskey,
    setUserHasPasskey,
    checkUserPasskeyEnrollment,
    postLogoutBanner,
    setPostLogoutBanner,
    postRedirectedBanner,
    setPostRedirectedBanner,
    postResetBanner,
    setPostResetBanner,
    emitLogoutBannerTelemetry,
    lockoutHelpText: recovery.lockoutHelpText,
    formattedRecoveryCountdown: recovery.formattedRecoveryCountdown,
    localLoading,
    showSuccess,
    focusedField,
    setFocusedField,
    lastUsedMethod,
    ssoCallbacks: ssoFlow.ssoCallbacks,
    showQR: ssoFlow.showQR,
    setShowQR: ssoFlow.setShowQR,
    qrUrl: ssoFlow.qrUrl,
    qrStatus: ssoFlow.qrStatus,
    ssoDiagnostics: ssoFlow.ssoDiagnostics,
    ssoProvider: ssoFlow.ssoProvider,
    magicLinkSent: ssoFlow.magicLinkSent,
    setMagicLinkSent: ssoFlow.setMagicLinkSent,
    magicLinkLoading: ssoFlow.magicLinkLoading,
    setMagicLinkLoading: ssoFlow.setMagicLinkLoading,
    magicLinkEmail: ssoFlow.magicLinkEmail,
    setMagicLinkEmail: ssoFlow.setMagicLinkEmail,
    isInIframe: ssoFlow.isInIframe,
    isInCrossOriginIframe: ssoFlow.isInCrossOriginIframe,
    logSsoTelemetry: ssoFlow.logSsoTelemetry,
    redirectToApp,
    isBusy,
    pwStrength,
    fadeIn,
    slideUp,
    startSsoDiagnostics: ssoFlow.startSsoDiagnostics,
    cancelSsoDiagnostics: ssoFlow.cancelSsoDiagnostics,
    handleSendMagicLink: ssoFlow.handleSendMagicLink,
    handleLogin,
    handleRequestOtp: otpFlow.handleRequestOtp,
    handleOtpLogin: otpFlow.handleOtpLogin,
    handleResendOTP: otpFlow.handleResendOTP,
    handle2FAVerify: otpFlow.handle2FAVerify,
    handlePinLogin,
    handlePasskeyLogin,
    showPasskeyEnrollmentPrompt,
    passkeyPromptBusy,
    handlePasskeyPromptDismiss,
    handlePasskeyPromptEnable,
    openSsoFullWindow: ssoFlow.openSsoFullWindow,
    handleGoogleLogin: ssoFlow.handleGoogleLogin,
    generateQR: ssoFlow.generateQR,
    handleMicrosoftLogin: ssoFlow.handleMicrosoftLogin,
    handleAppleLogin: ssoFlow.handleAppleLogin,
    setThemeMode,
  };
}
