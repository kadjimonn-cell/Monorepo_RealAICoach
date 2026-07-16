import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';
import api, { setCachedToken, clearCache } from '../services/api';
import type { AuthContextType, LogoutOptions, ServerSessionProbeResult, User } from './auth/types';
import {
  clearGuestModeFlag,
  clearPersistedSession,
  getSessionToken,
  loadUserSnapshot,
  persistSessionToken,
  persistUserSnapshot,
} from './auth/storage';
import { resolveRuntimeBaseUrl } from '../utils/runtimeBaseUrl';
import { resolveSsoPopupTargetOrigin } from '../utils/ssoMessagingSecurity';
import { clientLogger } from '../utils/clientLogger';
import { clearLastSidebarRoute } from '../hooks/useLastSidebarRoute';

import { useSessionReplay } from '../hooks/useSessionReplay';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { canonicalizeAdminIdentity, hasAdminConsoleVisibility } from '../utils/adminAccess';

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const AUTH_ME_TIMEOUT_MS = 3000;
const AUTH_ME_RETRY_BACKOFF_MS = [250, 700];
const AUTH_ME_COOKIE_BOOTSTRAP_TIMEOUT_MS = 1800;
const AUTH_ME_COOKIE_BOOTSTRAP_RETRY_BACKOFF_MS = [250];
const AUTH_ME_ROUTE_PROBE_TIMEOUT_MS = 2200;
const AUTH_ME_ROUTE_PROBE_RETRY_BACKOFF_MS = [200];
const AUTH_ME_THROTTLE_MS = 900;
const SESSION_RENEW_MIN_INTERVAL_MS = 4 * 60 * 60 * 1000;
const SESSION_RENEW_STORAGE_KEY = 'auth_last_renewal_at';

function sanitizeAuthUserPayload(payload: Record<string, any> | null | undefined): Record<string, any> {
  const next = { ...(canonicalizeAdminIdentity(payload || {}) || {}) };
  const profileImage = String(next.profile_image || '').trim();
  const picture = String(next.picture || '').trim();

  const isPlaceholderImage = (value: string) => value.startsWith('https://example.com/') || value.startsWith('http://example.com/');

  if (profileImage && isPlaceholderImage(profileImage)) {
    next.profile_image = '';
  }
  if (picture && isPlaceholderImage(picture)) {
    next.picture = '';
  }
  // Normalize admin flag at source-of-truth payload boundary.
  next.is_admin = hasAdminConsoleVisibility(next as any);
  return next;
}

function createAuthFlowError(error: any, fallbackMessage: string): Error {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const authError = new Error(String(detail.message || fallbackMessage));
    (authError as any).code = detail.code;
    (authError as any).retryAfterSeconds = detail.retry_after_seconds;
    (authError as any).blockedUntil = detail.blocked_until;
    (authError as any).lockedAt = detail.locked_at;
    (authError as any).failedAttempts = detail.failed_attempts;
    (authError as any).supportUrl = detail.support_url || detail.recovery?.support_url || '/contact';
    (authError as any).resetPasswordUrl = detail.reset_password_url || detail.recovery?.reset_password_url || '/auth/forgot-password';
    (authError as any).recoveryActions = detail.recovery_actions || [];
    (authError as any).displayMessage = detail.display_message || detail.message || '';
    (authError as any).nextSteps = Array.isArray(detail.next_steps) ? detail.next_steps : [];
    (authError as any).emailNotificationSent = Boolean(detail.email_notification_sent);
    (authError as any).riskCode = detail.risk_code || detail.code || '';
    (authError as any).riskLevel = detail.risk_engine?.risk_level || detail.risk_level || '';
    (authError as any).idvAccessToken = detail.idv_access_token || '';
    return authError;
  }
  if (typeof detail === 'string' && detail.trim()) {
    return new Error(detail);
  }
  return new Error(fallbackMessage);
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [welcomeBack, setWelcomeBack] = useState<{ name: string; lastRoute: string; lastActiveAt?: string } | null>(null);
  const authChecked = useRef(false);
  const authMeInFlightRef = useRef<Promise<any> | null>(null);
  const authMeLastAttemptAtRef = useRef(0);
  const sessionRenewInFlightRef = useRef(false);
  const telemetryThrottleRef = useRef<Record<string, number>>({});
  const lastKnownUserRef = useRef<User | null>(null);
  const authApiBase = resolveRuntimeBaseUrl();
  const webOrigin = Platform.OS === 'web' && typeof window !== 'undefined'
    ? window.location.origin.replace(/\/+$/, '')
    : authApiBase;

  const emitSsoTelemetry = useCallback((provider: string, phase: string, extra: Record<string, any> = {}) => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    let crossOriginIframe = false;
    if (window !== window.top) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      try { const _ = window.top?.location?.href; } catch { crossOriginIframe = true; }
    }
    api.post('/auth/sso-telemetry', {
      provider,
      phase,
      iframe_mode: window !== window.top,
      cross_origin_iframe: crossOriginIframe,
      context: 'auth_context',
      ...extra,
    }).catch(() => {});
  }, []);

  const emitSessionTelemetry = useCallback((reasonCode: string, extra: Record<string, any> = {}) => {
    const now = Date.now();
    const key = `${reasonCode}:${extra.phase || 'runtime'}`;
    const last = telemetryThrottleRef.current[key] || 0;
    if (now - last < 15000) return;
    telemetryThrottleRef.current[key] = now;

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        window.dispatchEvent(new CustomEvent('auth-session-telemetry', {
          detail: {
            reason_code: reasonCode,
            timestamp: new Date().toISOString(),
            ...extra,
          },
        }));
      } catch (error) { handleAppRecoverableError({ scope: 'src/context/AuthContext.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    api.post('/auth/session-bootstrap-telemetry', {
      reason_code: reasonCode,
      phase: extra.phase || 'runtime',
      status: typeof extra.status === 'number' ? extra.status : undefined,
      attempt: typeof extra.attempt === 'number' ? extra.attempt : undefined,
    }, { silentLoading: true }).catch(() => {});
    console.warn('[auth-session]', reasonCode, extra);
  }, []);

  const classifyAuthMeFailure = useCallback((error: any): { kind: 'unauthorized' | 'rate_limited' | 'timeout' | 'network' | 'server' | 'unknown'; status: number } => {
    const status = Number(error?.response?.status || 0);
    if (status === 401) return { kind: 'unauthorized', status };
    if (status === 429) return { kind: 'rate_limited', status };
    if (status >= 500) return { kind: 'server', status };

    const name = String(error?.name || '').toLowerCase();
    const message = String(error?.message || '').toLowerCase();
    if (name.includes('abort') || message.includes('abort') || message.includes('timeout')) {
      return { kind: 'timeout', status };
    }
    if (!status || message.includes('network')) {
      return { kind: 'network', status };
    }
    return { kind: 'unknown', status };
  }, []);

  const applyAuthenticatedUser = useCallback(async (rawUser: Record<string, any>) => {
    const sanitizedUser = sanitizeAuthUserPayload(rawUser);
    setUser(sanitizedUser as User);
    lastKnownUserRef.current = sanitizedUser as User;
    await persistUserSnapshot(sanitizedUser as User);
    return sanitizedUser as User;
  }, []);

  const renewSessionIfDue = useCallback(async (phase: string) => {
    if (Platform.OS !== 'web') return;
    if (sessionRenewInFlightRef.current) return;
    const now = Date.now();
    let lastRenewAt = 0;
    try {
      const fromStorage = await AsyncStorage.getItem(SESSION_RENEW_STORAGE_KEY);
      lastRenewAt = Number(fromStorage || 0);
      if (!Number.isFinite(lastRenewAt)) lastRenewAt = 0;
    } catch {
      lastRenewAt = 0;
    }
    if (lastRenewAt && now - lastRenewAt < SESSION_RENEW_MIN_INTERVAL_MS) return;

    sessionRenewInFlightRef.current = true;
    try {
      const response = await api.post('/auth/renew-session', {}, { silentLoading: true });
      const nextToken = response?.data?.session_token;
      if (nextToken) {
        await persistSessionToken(nextToken);
      }
      await AsyncStorage.setItem(SESSION_RENEW_STORAGE_KEY, String(Date.now()));
      emitSessionTelemetry('session_renew_success', { phase });
    } catch (error: any) {
      const failure = classifyAuthMeFailure(error);
      emitSessionTelemetry('session_renew_failed', { phase, kind: failure.kind, status: failure.status || undefined });
    } finally {
      sessionRenewInFlightRef.current = false;
    }
  }, [classifyAuthMeFailure, emitSessionTelemetry]);

  const fetchAuthMeResilient = useCallback(async (
    options: {
      phase: string;
      snapshot: User | null;
      force?: boolean;
      retryOnTransient?: boolean;
      timeoutMs?: number;
      retryBackoffMs?: number[];
    }
  ): Promise<{ state: 'authenticated'; user: User } | { state: 'unauthorized'; status: number } | { state: 'transient'; kind: string; status: number; snapshot: User | null }> => {
    const {
      phase,
      snapshot,
      force = false,
      retryOnTransient = true,
      timeoutMs = AUTH_ME_TIMEOUT_MS,
      retryBackoffMs = AUTH_ME_RETRY_BACKOFF_MS,
    } = options;
    const now = Date.now();

    if (!force && authMeInFlightRef.current) {
      return authMeInFlightRef.current;
    }
    if (!force && now - authMeLastAttemptAtRef.current < AUTH_ME_THROTTLE_MS) {
      const cached = lastKnownUserRef.current || snapshot;
      if (cached) {
        return { state: 'authenticated', user: cached };
      }
    }

    authMeLastAttemptAtRef.current = now;

    const task = (async () => {
      let attempt = 0;
      while (attempt <= retryBackoffMs.length) {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), timeoutMs);
        try {
          const response = await api.get('/auth/me', {
            signal: controller.signal,
            silentLoading: true,
          });
          clearTimeout(timeout);
          const sanitizedUser = await applyAuthenticatedUser(response.data);
          void renewSessionIfDue(`${phase}_auth_me_success`);
          return { state: 'authenticated' as const, user: sanitizedUser };
        } catch (error: any) {
          clearTimeout(timeout);
          const failure = classifyAuthMeFailure(error);
          const isRetryable = retryOnTransient && ['rate_limited', 'timeout', 'network', 'server'].includes(failure.kind);

          emitSessionTelemetry(`auth_me_${failure.kind}`, {
            phase,
            status: failure.status || undefined,
            attempt,
          });

          if (failure.kind === 'unauthorized') {
            return { state: 'unauthorized' as const, status: failure.status };
          }

          if (isRetryable && attempt < retryBackoffMs.length) {
            const backoff = retryBackoffMs[attempt];
            await new Promise((resolve) => setTimeout(resolve, backoff));
            attempt += 1;
            continue;
          }

          return {
            state: 'transient' as const,
            kind: failure.kind,
            status: failure.status,
            snapshot,
          };
        }
      }

      return {
        state: 'transient' as const,
        kind: 'unknown',
        status: 0,
        snapshot,
      };
    })();

    authMeInFlightRef.current = task;
    try {
      return await task;
    } finally {
      if (authMeInFlightRef.current === task) {
        authMeInFlightRef.current = null;
      }
    }
  }, [applyAuthenticatedUser, classifyAuthMeFailure, emitSessionTelemetry, renewSessionIfDue]);

  useEffect(() => {
    if (!authChecked.current) {
      authChecked.current = true;
      checkAuth();
    }
    
    const handleUrl = async (url: string) => {
      if (url.includes('session_id=')) {
        const sessionId = url.split('session_id=')[1]?.split('&')[0]?.split('#')[0];
        if (sessionId) {
          await handleGoogleCallback(sessionId);
        }
      }
    };

    Linking.getInitialURL().then((url) => {
      if (url) handleUrl(url);
    });

    const subscription = Linking.addEventListener('url', (event) => {
      handleUrl(event.url);
    });

    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const hash = window.location.hash;
      const isPopup = !!window.opener;
      if (hash.includes('session_id=')) {
        const sessionId = hash.split('session_id=')[1]?.split('&')[0];
        if (sessionId) {
          if (isPopup) {
            // Opened as popup from iframe — exchange session_id, relay token back, and close
            (async () => {
              try {
                const response = await api.post('/auth/google/session', { session_id: sessionId });
                const { session_token } = response.data;
                emitSsoTelemetry('google', 'callback_received', { popup_method: 'session_exchange_popup' });
                const targetOrigin = resolveSsoPopupTargetOrigin();
                if (targetOrigin) {
                  if (session_token) {
                    window.opener.postMessage({ type: 'sso_token', token: session_token, provider: 'google' }, targetOrigin);
                  } else {
                    window.opener.postMessage({ type: 'sso_complete', provider: 'google' }, targetOrigin);
                  }
                }
              } catch (e) {
                emitSsoTelemetry('google', 'callback_error', { note: 'popup session exchange failed' });
                console.error('Google popup relay error:', e);
              }
              setTimeout(() => { try { window.close(); } catch (error) { handleAppRecoverableError({ scope: 'src/context/AuthContext.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 500);
            })();
          } else {
            handleGoogleCallback(sessionId);
          }
          window.history.replaceState(null, '', window.location.pathname);
        }
      }
      // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
      if (hash.includes('ms_session_token=')) {
        emitSsoTelemetry('microsoft', 'callback_error', { note: 'token_in_url_rejected' });
        window.history.replaceState(null, '', window.location.pathname);
        setLoading(false);
      }
    }

    return () => { subscription.remove(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emitSsoTelemetry]);

  const checkAuth = useCallback(async () => {
    try {
      const token = await getSessionToken();
      const webCookieOnly = Platform.OS === 'web';
      const snapshot = await loadUserSnapshot();
      const hasSessionHint = Boolean(snapshot?.user_id || snapshot?.email || snapshot?.subscription_plan);

      // Strict auth: guest mode is disabled platform-wide
      await clearGuestModeFlag();

      if (token) {
        setCachedToken(token);
        const authOutcome = await fetchAuthMeResilient({
          phase: 'bootstrap_token',
          snapshot,
          retryOnTransient: true,
          timeoutMs: AUTH_ME_TIMEOUT_MS,
          retryBackoffMs: AUTH_ME_RETRY_BACKOFF_MS,
        });

        if (authOutcome.state === 'authenticated') {
          setUser(authOutcome.user);
          lastKnownUserRef.current = authOutcome.user;
        } else if (authOutcome.state === 'unauthorized') {
          setUser(null);
          setCachedToken(null);
          await clearPersistedSession();
        } else {
          // Never promote persisted snapshots into authenticated session state.
          // Protected routes must only unlock after a verified server-auth success.
          setUser(null);
        }
      } else if (webCookieOnly) {
        // Cookie-only web auth: session is validated via HttpOnly cookie.
        const authOutcome = await fetchAuthMeResilient({
          phase: 'bootstrap_cookie_only',
          snapshot,
          retryOnTransient: hasSessionHint,
          timeoutMs: hasSessionHint ? AUTH_ME_TIMEOUT_MS : AUTH_ME_COOKIE_BOOTSTRAP_TIMEOUT_MS,
          retryBackoffMs: hasSessionHint ? AUTH_ME_COOKIE_BOOTSTRAP_RETRY_BACKOFF_MS : [],
        });

        if (authOutcome.state === 'authenticated') {
          setUser(authOutcome.user);
          lastKnownUserRef.current = authOutcome.user;
        } else if (authOutcome.state === 'unauthorized') {
          setUser(null);
          await clearPersistedSession();
        } else {
          // Never promote persisted snapshots into authenticated session state.
          // Protected routes must only unlock after a verified server-auth success.
          // Keep null but avoid wiping persisted state on transient startup transport errors.
          setUser(null);
        }
      }
    } catch {
      clientLogger.log('Not authenticated');
    } finally {
      setLoading(false);
    }
  }, [fetchAuthMeResilient]);

  const applyAuthSession = useCallback(
    async (
      payload: Record<string, any>,
      options: { clearApiCache?: boolean } = {},
    ): Promise<User> => {
      const { session_token, refresh_token, ...rawUserData } = payload;
      const userData = await applyAuthenticatedUser(rawUserData);
      if (session_token) {
        await persistSessionToken(session_token);
      }
      if (refresh_token && Platform.OS !== 'web') {
        await AsyncStorage.setItem('refresh_token', refresh_token);
      }
      if (options.clearApiCache !== false) {
        clearCache();
      }
      return userData;
    },
    [applyAuthenticatedUser],
  );

  const handleGoogleCallback = useCallback(async (sessionId: string) => {
    setLoading(true);
    try {
      const response = await api.post('/auth/google/session', { session_id: sessionId });

      emitSsoTelemetry('google', 'callback_received', { popup_method: 'session_exchange' });
      await applyAuthSession(response.data, { clearApiCache: false });
    } catch (error) {
      emitSsoTelemetry('google', 'callback_error', { note: 'session exchange failed' });
      console.error('Google auth error:', error);
    } finally {
      setLoading(false);
    }
  }, [emitSsoTelemetry, applyAuthSession]);

  const login = useCallback(async (email: string, password: string, rememberMe?: boolean, resendOtp?: boolean): Promise<any> => {
    try {
      const response = await api.post('/auth/login', {
        email,
        password,
        remember_me: !!rememberMe,
        resend_otp: !!resendOtp,
      });
      
      // Check if 2FA is required - return the data instead of throwing
      if (response.data.requires_2fa) {
        return {
          requires_2fa: true,
          user_id: response.data.user_id,
          email: response.data.email,
          otp_hint: response.data.otp_hint,
          otp_method: response.data.otp_method,
          code_reused: response.data.code_reused,
          code_expires_in_minutes: response.data.code_expires_in_minutes,
          otp_delivery_status: response.data.otp_delivery_status,
          remember_me: response.data.remember_me,
          risk_level: response.data.risk_level,
          risk_score: response.data.risk_score,
          risk_output: response.data.risk_output,
          display_message: response.data.display_message,
          next_steps: response.data.next_steps,
          email_notification_sent: response.data.email_notification_sent,
          risk_code: response.data.risk_code,
          support_url: response.data.support_url,
          idv_access_token: response.data.idv_access_token,
        };
      }
      
      const { welcome_back: wb, last_active_route, last_active_at } = response.data;
      const userData = await applyAuthSession(response.data);

      // Handle welcome back
      if (wb && last_active_route) {
        setWelcomeBack({ name: userData.name, lastRoute: last_active_route, lastActiveAt: last_active_at });
      }

      return { success: true, welcome_back: wb, last_active_route };
    } catch (error: any) {
      throw createAuthFlowError(error, 'Login failed');
    }
  }, [applyAuthSession]);

  const requestOtp = useCallback(async (email: string, forceResend?: boolean) => {
    try {
      const response = await api.post('/auth/otp/request', { email, force_resend: !!forceResend });
      return response.data || {};
    } catch (error: any) {
      throw createAuthFlowError(error, 'Failed to request code');
    }
  }, []);

  const loginWithOtp = useCallback(async (email: string, code: string): Promise<any> => {
    try {
      const response = await api.post('/auth/otp/verify', { email, code });
      await applyAuthSession(response.data);
      return { success: true };
    } catch (error: any) {
      throw createAuthFlowError(error, 'OTP login failed');
    }
  }, [applyAuthSession]);

  const verify2FA = useCallback(async (userId: string, code: string, rememberMe?: boolean): Promise<any> => {
    try {
      const response = await api.post('/auth/2fa/verify', { user_id: userId, code, remember_me: !!rememberMe });
      const { welcome_back: wb, last_active_route, last_active_at } = response.data;
      const userData = await applyAuthSession(response.data);
      await fetchAuthMeResilient({ phase: 'post-2fa', snapshot: null, force: true });

      if (wb && last_active_route) {
        setWelcomeBack({ name: userData.name, lastRoute: last_active_route, lastActiveAt: last_active_at });
      }

      return { success: true, welcome_back: wb, last_active_route };
    } catch (error: any) {
      throw createAuthFlowError(error, 'Verification failed');
    }
  }, [applyAuthSession, fetchAuthMeResilient]);

  const verifyPin = useCallback(async (userId: string, pin: string) => {
    try {
      const response = await api.post('/auth/biometric/verify-pin', { user_id: userId, pin });
      await applyAuthSession(response.data);
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'PIN verification failed');
    }
  }, [applyAuthSession]);

  const register = useCallback(async (email: string, password: string, name: string) => {
    try {
      const response = await api.post('/auth/register', { email, password, name });
      await applyAuthSession(response.data);
    } catch (error: any) {
      throw new Error(error.response?.data?.detail || 'Registration failed');
    }
  }, [applyAuthSession]);

  const loginWithGoogle = useCallback(async () => {
    try {
      // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
      const redirectUrl = Platform.OS === 'web'
        ? `${webOrigin}/`
        : Linking.createURL('/');
      
      const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
      
      if (Platform.OS === 'web') {
        const inIframe = window !== window.top;
        if (inIframe) {
          window.open(authUrl, 'google_sso_popup', 'width=500,height=700,left=200,top=100');
        } else {
          window.location.href = authUrl;
        }
      } else {
        const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
        if (result.type === 'success' && result.url) {
          if (result.url.includes('session_id=')) {
            const sessionId = result.url.split('session_id=')[1]?.split('&')[0]?.split('#')[0];
            if (sessionId) await handleGoogleCallback(sessionId);
          }
        }
      }
    } catch (error) {
      console.error('Google login error:', error);
    }
  }, [handleGoogleCallback, webOrigin]);

  const loginWithMicrosoft = useCallback(async () => {
    try {
      const url = `${authApiBase}/api/auth/microsoft/login`;
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const inIframe = window !== window.top;
        if (inIframe) {
          window.open(url, 'ms_sso_popup', 'width=500,height=700,left=200,top=100');
        } else {
          let canAccessTop = false;
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          try { const _ = window.top?.location?.href; canAccessTop = true; } catch { canAccessTop = false; }
          if (canAccessTop && window.top && window.top !== window) {
            window.top.location.href = url;
          } else {
            window.location.href = url;
          }
        }
      } else {
        await Linking.openURL(url);
      }
    } catch (error) {
      console.error('Microsoft login error:', error);
    }
  }, [authApiBase]);

  const logout = useCallback(async (options: LogoutOptions = {}) => {
    const routePath = Platform.OS === 'web' && typeof window !== 'undefined'
      ? window.location.pathname
      : 'native';
    const telemetryPayload = {
      action: 'logout_initiated',
      reason: options.reason || 'user_initiated',
      source: options.source || routePath,
      route_path: routePath,
      redirect_target: options.redirectTarget || '/auth/login?logout=1',
      expected_logout_banner: options.expectedLogoutBanner ?? true,
      platform: Platform.OS,
      initiated_at: new Date().toISOString(),
      user_id: (user as any)?.user_id || null,
      email: (user as any)?.email || null,
      tenant_id: (user as any)?.tenant_id || null,
      organization_id: (user as any)?.organization_id || null,
      company_id: (user as any)?.company_id || null,
      workspace_id: (user as any)?.workspace_id || null,
    };

    const logoutRequest = api.post('/auth/logout', telemetryPayload, { silentLoading: true }).catch(() => {});

    try {
      setUser(null);
      lastKnownUserRef.current = null;
      setCachedToken(null);
      clearCache();
      // Clear the persisted "last sidebar route" so the next user
      // signing in (or this user signing back in) doesn't get warped
      // back to the previous session's route. Lazy require so this
      // module is safe to pull into native-only bundles where
      // localStorage doesn't exist.
      try {
        clearLastSidebarRoute();
      } catch { /* noop */ }
      const removePromise = clearPersistedSession();
      await Promise.race([
        removePromise,
        new Promise((resolve) => setTimeout(resolve, 500)),
      ]);
    } catch (error) {
      console.error('Logout error:', error);
    }

    await Promise.race([
      logoutRequest,
      new Promise((resolve) => setTimeout(resolve, 700)),
    ]);
  }, [user]);

  const loginAsGuest = useCallback(async () => {
    throw new Error('Guest access is disabled. Please sign in to continue.');
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const snapshot = await loadUserSnapshot();
      const authOutcome = await fetchAuthMeResilient({
        phase: 'refresh_user',
        snapshot,
        retryOnTransient: true,
      });

      if (authOutcome.state === 'authenticated') {
        setUser(authOutcome.user);
        lastKnownUserRef.current = authOutcome.user;
        return;
      }

      if (authOutcome.state === 'unauthorized') {
        setUser(null);
        lastKnownUserRef.current = null;
        setCachedToken(null);
        await clearPersistedSession();
        return;
      }

      // Never promote persisted snapshots into authenticated session state.
      // If refresh is transient, keep the current verified in-memory session if one exists.
    } catch (error) { handleAppRecoverableError({ scope: 'src/context/AuthContext.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [fetchAuthMeResilient]);

  const probeServerSession = useCallback(async (): Promise<ServerSessionProbeResult> => {
    const snapshot = await loadUserSnapshot();
    const authOutcome = await fetchAuthMeResilient({
      phase: 'route_guard_session_probe',
      snapshot,
      force: true,
      retryOnTransient: true,
      timeoutMs: AUTH_ME_ROUTE_PROBE_TIMEOUT_MS,
      retryBackoffMs: AUTH_ME_ROUTE_PROBE_RETRY_BACKOFF_MS,
    });
    if (authOutcome.state === 'authenticated') {
      return { state: 'authenticated' };
    }
    if (authOutcome.state === 'unauthorized') {
      return { state: 'unauthenticated', status: authOutcome.status };
    }
    return {
      state: 'transient',
      status: authOutcome.status || undefined,
      kind: String(authOutcome.kind || 'unknown'),
    };
  }, [fetchAuthMeResilient]);

  const hasServerSession = useCallback(async (): Promise<boolean> => {
    const probe = await probeServerSession();
    return probe.state === 'authenticated';
  }, [probeServerSession]);

  const clearWelcomeBack = useCallback(() => {
    setWelcomeBack(null);
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || !user?.user_id) return;
    const interval = setInterval(() => {
      void renewSessionIfDue('periodic_interval');
    }, 15 * 60 * 1000);
    return () => clearInterval(interval);
  }, [renewSessionIfDue, user?.user_id]);

  const canUseAdminReplay = hasAdminConsoleVisibility(user as any);

  // Session replay: silently capture user interactions
  useSessionReplay(canUseAdminReplay ? user?.user_id : undefined, canUseAdminReplay ? user?.email : undefined);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        guest: false,
        loginAsGuest,
        login,
        requestOtp,
        loginWithOtp,
        verify2FA,
        verifyPin,
        register,
        loginWithGoogle,
        loginWithMicrosoft,
        logout,
        refreshUser,
        hasServerSession,
        probeServerSession,
        welcomeBack,
        clearWelcomeBack,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
