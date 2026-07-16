import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api, { setCachedToken } from '../../../services/api';
import { isTrustedSsoMessageOrigin, resolveSsoPopupTargetOrigin } from '../../../utils/ssoMessagingSecurity';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';
import { isValidAuthQrPayload, normalizeAuthQrPayload } from './authQrContract';

type UseLoginSsoParams = {
  email: string;
  tx: (key: string, fallback: string) => string;
  setError: (value: string) => void;
  webOrigin: string;
  liveApiBase: string;
  isMobile: boolean;
  user: any;
  showSuccess: boolean;
  loginWithGoogle: () => Promise<any>;
  loginWithMicrosoft: () => Promise<any>;
  refreshUser: () => Promise<any>;
  redirectToApp: (lastRoute?: string, platformRole?: string | null) => void;
  saveLastMethod: (method: string) => Promise<void>;
};

export function useLoginSso({
  email,
  tx,
  setError,
  webOrigin,
  liveApiBase,
  isMobile,
  user,
  showSuccess,
  loginWithGoogle,
  loginWithMicrosoft,
  refreshUser,
  redirectToApp,
  saveLastMethod,
}: UseLoginSsoParams) {
  const getInitialSsoError = (): string | null => {
    try {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        return new URLSearchParams(window.location.search).get('sso_error');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    return null;
  };

  const [ssoErrorCode, setSsoErrorCode] = useState<string | null>(getInitialSsoError);
  const [ssoDiagnostics, setSsoDiagnostics] = useState<'idle' | 'waiting' | 'fallback'>('idle');
  const [ssoProvider, setSsoProvider] = useState<string>('');
  const [magicLinkSent, setMagicLinkSent] = useState(false);
  const [magicLinkLoading, setMagicLinkLoading] = useState(false);
  const [magicLinkEmail, setMagicLinkEmail] = useState('');
  const [ssoCallbacks, setSsoCallbacks] = useState<{ microsoft?: string; apple?: string } | null>(null);
  const [showQR, setShowQR] = useState(false);
  const [qrUrl, setQrUrl] = useState('');
  const [qrStatus, setQrStatus] = useState<'idle' | 'generating' | 'pending' | 'approved' | 'expired' | 'error'>('idle');
  const [isInIframe, setIsInIframe] = useState(false);
  const [isInCrossOriginIframe, setIsInCrossOriginIframe] = useState(false);

  const ssoDiagTimerRef = useRef<any>(null);
  const qrPollRef = useRef<any>(null);

  const persistSessionToken = useCallback(async (token: string, method: string) => {
    if (Platform.OS === 'web') {
      setCachedToken(null);
    } else {
      await AsyncStorage.setItem('session_token', token);
      setCachedToken(token);
      try { localStorage.setItem('session_token', token); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    try { await AsyncStorage.setItem('last_login_method', method); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    try { localStorage.setItem('last_login_method', method); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    await refreshUser();
    redirectToApp();
  }, [redirectToApp, refreshUser]);

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
  }, [isInCrossOriginIframe, isInIframe]);

  const startSsoDiagnostics = useCallback((provider: string) => {
    setSsoProvider(provider);
    setSsoDiagnostics('waiting');
    setMagicLinkEmail(email || '');
    if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
    ssoDiagTimerRef.current = setTimeout(() => {
      setSsoDiagnostics('fallback');
    }, 8000);
  }, [email]);

  const cancelSsoDiagnostics = useCallback(() => {
    if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
    setSsoDiagnostics('idle');
  }, []);

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
    try {
      void window.top?.location?.href;
    } catch {
      setIsInCrossOriginIframe(true);
    }
  }, []);

  useEffect(() => {
    if (user || showSuccess) {
      cancelSsoDiagnostics();
    }
  }, [cancelSsoDiagnostics, showSuccess, user]);

  useEffect(() => {
    return () => {
      if (ssoDiagTimerRef.current) clearTimeout(ssoDiagTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || !ssoErrorCode || (ssoErrorCode !== 'invalid_request' && ssoErrorCode !== 'token_failed')) return;
    api.get('/auth/sso-config', { silentLoading: true }).then((res) => {
      setSsoCallbacks({
        microsoft: res.data?.microsoft_callback,
        apple: res.data?.apple_callback,
      });
    }).catch(() => {});
  }, [ssoErrorCode]);

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
      setTimeout(() => {
        try { window.close(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }, 400);
    } else if (window.location.hash.includes('ms_session_token=') || window.location.hash.includes('apple_session_token=')) {
      // Strict mode: reject token-in-URL SSO callbacks.
      setError(tx('login.errors.failedTryAgain', 'Secure SSO callback failed. Please try again.'));
    }
  }, []);

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
        await persistSessionToken(token, provider);
      } catch (err) {
        logSsoTelemetry(provider, 'callback_error', { note: 'postmessage token processing failed' });
        console.error('SSO popup token processing error:', err);
        setError(tx('login.errors.failedTryAgain', 'Login failed. Please try again.'));
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [cancelSsoDiagnostics, isInIframe, logSsoTelemetry, persistSessionToken, redirectToApp, refreshUser, setError, tx]);

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
          await persistSessionToken(res.data.session_token, 'magic_link');
        } else {
          setCachedToken(null);
          await refreshUser();
          redirectToApp();
        }
      } catch (err: any) {
        setError(err?.response?.data?.detail || 'Magic link expired or invalid. Please request a new one.');
      }
    })();
  }, [persistSessionToken, redirectToApp, refreshUser, setError]);

  const handleSendMagicLink = useCallback(async () => {
    if (!magicLinkEmail) {
      setError(tx('login.magicLink.enterEmailFirst', 'Please enter your email first'));
      return;
    }
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
  }, [magicLinkEmail, setError, tx]);

  const openSsoPopup = useCallback((url: string, windowName: string, provider: string) => {
    startSsoDiagnostics(provider);
    logSsoTelemetry(provider, 'popup_attempt');

    try {
      const popup = window.open(url, windowName, 'width=500,height=700,left=200,top=100');
      if (popup && !popup.closed) {
        logSsoTelemetry(provider, 'popup_opened', { popup_method: 'window_open' });
        return;
      }
    } catch (e) {
      console.warn(`[SSO] window.open() failed for ${provider}:`, e);
    }

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
      return;
    } catch (e) {
      console.warn(`[SSO] Dynamic anchor failed for ${provider}:`, e);
    }

    logSsoTelemetry(provider, 'popup_failed', { note: 'window_open and dynamic_anchor failed' });
    setSsoDiagnostics('fallback');
  }, [logSsoTelemetry, startSsoDiagnostics]);

  const openSsoFullWindow = useCallback((url: string, provider: string) => {
    logSsoTelemetry(provider, 'direct_redirect', { popup_method: 'full_window' });
    try {
      if (isInIframe || isInCrossOriginIframe) {
        const popup = window.open(url, '_blank', 'noopener,noreferrer');
        if (popup && !popup.closed) return;
      }
      (window.top || window).location.href = url;
    } catch {
      window.location.href = url;
    }
  }, [isInCrossOriginIframe, isInIframe, logSsoTelemetry]);

  const handleGoogleLogin = useCallback(async () => {
    try {
      await saveLastMethod('google');
      logSsoTelemetry('google', 'click');
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const url = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(window.location.origin + '/')}`;
        if (isInIframe) {
          openSsoPopup(url, 'sso_google_popup', 'Google');
        } else {
          logSsoTelemetry('google', 'direct_redirect', { popup_method: 'top_navigation' });
          (window.top || window).location.href = url;
        }
      } else {
        await loginWithGoogle();
      }
    } catch {
      setError('Google login failed');
    }
  }, [isInIframe, logSsoTelemetry, loginWithGoogle, openSsoPopup, saveLastMethod, setError]);

  const handleMicrosoftLogin = useCallback(() => {
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
  }, [isInIframe, isMobile, liveApiBase, logSsoTelemetry, loginWithMicrosoft, openSsoFullWindow, saveLastMethod]);

  const handleAppleLogin = useCallback(() => {
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
  }, [isInIframe, isMobile, liveApiBase, logSsoTelemetry, openSsoFullWindow, saveLastMethod]);

  const generateQR = useCallback(async () => {
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

      const sessionId = res.data.session_id;
      if (qrPollRef.current) clearInterval(qrPollRef.current);
      qrPollRef.current = setInterval(async () => {
        try {
          const statusRes = await api.get(`/auth/qr/status/${sessionId}`);
          if (statusRes.data.status === 'approved' && statusRes.data.session_token) {
            clearInterval(qrPollRef.current);
            qrPollRef.current = null;
            // On web with cookie auth, use the consume endpoint to set the session cookie
            if (Platform.OS === 'web') {
              try {
                await api.post('/auth/qr/consume', {
                  session_id: sessionId,
                  session_token: statusRes.data.session_token,
                });
                // Cookie is now set — refresh user and redirect
                await refreshUser();
                redirectToApp();
              } catch {
                // Fallback: try the token-based approach
                await persistSessionToken(statusRes.data.session_token, 'qr');
              }
            } else {
              await persistSessionToken(statusRes.data.session_token, 'qr');
            }
          } else if (statusRes.data.status === 'expired') {
            clearInterval(qrPollRef.current);
            qrPollRef.current = null;
            setQrStatus('expired');
          }
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/useLoginSso.ts#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }, 2000);
    } catch (e: any) {
      setQrStatus('error');
      setError(e?.response?.data?.detail || 'Failed to generate QR code');
    }
  }, [persistSessionToken, setError, refreshUser, redirectToApp]);

  useEffect(() => {
    return () => {
      if (qrPollRef.current) clearInterval(qrPollRef.current);
    };
  }, []);

  return {
    ssoErrorCode,
    setSsoErrorCode,
    ssoDiagnostics,
    ssoProvider,
    magicLinkSent,
    setMagicLinkSent,
    magicLinkLoading,
    setMagicLinkLoading,
    magicLinkEmail,
    setMagicLinkEmail,
    ssoCallbacks,
    showQR,
    setShowQR,
    qrUrl,
    qrStatus,
    isInIframe,
    isInCrossOriginIframe,
    logSsoTelemetry,
    startSsoDiagnostics,
    cancelSsoDiagnostics,
    handleSendMagicLink,
    openSsoFullWindow,
    handleGoogleLogin,
    handleMicrosoftLogin,
    handleAppleLogin,
    generateQR,
  };
}
