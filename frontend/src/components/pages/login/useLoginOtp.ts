import { useCallback, useState } from 'react';
import { Alert, Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api, { setCachedToken } from '../../../services/api';
import {
  isPasskeySupportedOnWeb,
  normalizeAuthenticationOptions,
  serializeWebAuthnCredential,
} from '../../../utils/webauthn';

type UseLoginOtpParams = {
  email: string;
  setEmail: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
  rememberMe: boolean;
  setPostResetBanner: (value: boolean) => void;
  setPostLogoutBanner: (value: boolean) => void;
  setLogoutRedirectHold: (value: boolean) => void;
  tx: (key: string, fallback: string) => string;
  login: (email: string, password: string, remember?: boolean, resend_2fa?: boolean) => Promise<any>;
  requestOtp: (email: string, forceResend?: boolean) => Promise<any>;
  loginWithOtp: (email: string, code: string) => Promise<any>;
  verify2FA: (userId: string, code: string, remember?: boolean) => Promise<any>;
  clearAuthIssue: () => void;
  handleAuthError: (err: any, fallback: string) => void;
  setAuthRecovery: (value: any) => void;
  setError: (value: string) => void;
  redirectToApp: (lastRoute?: string, platformRole?: string | null) => void;
  saveLastMethod: (method: string) => Promise<void>;
  getWebInputValue: (testId: string, placeholder?: string) => string;
  refreshUser: () => Promise<any>;
  onPasswordLoginSuccess?: (result: any) => Promise<boolean> | boolean;
};

export function useLoginOtp({
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
  clearAuthIssue,
  handleAuthError,
  setAuthRecovery,
  setError,
  redirectToApp,
  saveLastMethod,
  getWebInputValue,
  refreshUser,
  onPasswordLoginSuccess,
}: UseLoginOtpParams) {
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

  const handleLogin = useCallback(async () => {
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

    if (!effectiveEmail || !effectivePassword) {
      setError(tx('login.errors.fillAllFields', 'Please fill in all fields'));
      return;
    }

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
      if (onPasswordLoginSuccess) {
        const handled = await onPasswordLoginSuccess(result);
        if (handled) return;
      }
      redirectToApp(result?.last_active_route);
    } catch (err: any) {
      handleAuthError(err, tx('login.errors.failed', 'Login failed'));
    }
  }, [
    clearAuthIssue,
    email,
    getWebInputValue,
    handleAuthError,
    login,
    password,
    redirectToApp,
    rememberMe,
    saveLastMethod,
    setAuthRecovery,
    setError,
    setEmail,
    setLogoutRedirectHold,
    setPassword,
    setPostLogoutBanner,
    setPostResetBanner,
    tx,
    onPasswordLoginSuccess,
  ]);

  const handleRequestOtp = useCallback(async () => {
    if (!email) {
      setError(tx('login.otp.emailRequired', 'Email is required for OTP login'));
      return;
    }
    try {
      clearAuthIssue();
      setOtpLoginLoading(true);
      const response = await requestOtp(email, otpLoginRequested);
      const codeReused = Boolean(response?.code_reused);
      if (codeReused) {
        setOtpLoginHint(tx('login.otp.codeStillValid', 'Your existing verification code is still valid. Check your email inbox.'));
      } else if (otpLoginRequested) {
        setOtpLoginHint(tx('login.otp.newCodeSent', 'A new verification code has been sent to your email inbox.'));
      } else {
        setOtpLoginHint(response?.otp_hint || tx('login.otp.checkEmailCode', 'Check your email for the 8-digit code.'));
      }
      setOtpLoginRequested(true);
      setOtpLoginCode('');
    } catch (err: any) {
      handleAuthError(err, 'Failed to request code');
    } finally {
      setOtpLoginLoading(false);
    }
  }, [clearAuthIssue, email, handleAuthError, otpLoginRequested, requestOtp, setError, tx]);

  const handleOtpLogin = useCallback(async () => {
    if (!email || !otpLoginCode) {
      setError(tx('login.otp.emailCodeRequired', 'Email and code are required'));
      return;
    }
    if (otpLoginCode.replace(/\D/g, '').length !== 8) {
      setError(tx('login.otp.enterEightDigits', 'Please enter the 8-digit code'));
      return;
    }
    try {
      clearAuthIssue();
      const result = await loginWithOtp(email, otpLoginCode);
      await saveLastMethod('otp');
      if (onPasswordLoginSuccess) {
        const handled = await onPasswordLoginSuccess(result);
        if (handled) return;
      }
      redirectToApp(result?.last_active_route);
    } catch (err: any) {
      handleAuthError(err, tx('login.otp.failed', 'OTP login failed'));
    }
  }, [clearAuthIssue, email, handleAuthError, loginWithOtp, onPasswordLoginSuccess, otpLoginCode, redirectToApp, saveLastMethod, setError, tx]);

  const handleResendOTP = useCallback(async () => {
    if (resending) return;
    const resendEmail = pendingAuthEmail || email.trim();
    const resendPassword = pendingAuthPassword || password;
    if (!resendEmail || !resendPassword) {
      setError(tx('login.otp.resendNeedsCredentials', 'Please sign in again to request a fresh verification code.'));
      return;
    }
    setResending(true);
    setError('');
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
      if (onPasswordLoginSuccess) {
        const handled = await onPasswordLoginSuccess(result);
        if (handled) return;
      }
      redirectToApp(result?.last_active_route);
    } catch (err: any) {
      handleAuthError(err, tx('login.otp.verificationFailed', 'Verification failed'));
    } finally {
      setResending(false);
    }
  }, [
    email,
    handleAuthError,
    login,
    password,
    pendingAuthEmail,
    pendingAuthPassword,
    pendingRememberMe,
    redirectToApp,
    resending,
    saveLastMethod,
    setError,
    tx,
    onPasswordLoginSuccess,
  ]);

  const handle2FAVerify = useCallback(async () => {
    if (otpCode.replace(/\D/g, '').length !== 8) {
      setError(tx('login.otp.enterEightDigits', 'Please enter the 8-digit code'));
      return;
    }
    clearAuthIssue();
    try {
      const result = await verify2FA(pending2FAUserId, otpCode, pendingRememberMe);
      setShow2FA(false);
      setPendingAuthPassword('');
      await saveLastMethod('password');
      if (onPasswordLoginSuccess) {
        const handled = await onPasswordLoginSuccess(result);
        if (handled) return;
      }
      redirectToApp(result?.last_active_route);
    } catch (err: any) {
      handleAuthError(err, tx('login.otp.verificationFailed', 'Verification failed'));
    }
  }, [
    clearAuthIssue,
    handleAuthError,
    otpCode,
    pending2FAUserId,
    pendingRememberMe,
    redirectToApp,
    saveLastMethod,
    setError,
    tx,
    verify2FA,
    onPasswordLoginSuccess,
  ]);

  const handlePinLogin = useCallback(async (pin: string) => {
    try {
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(email)}`);
      if (!lookup.data?.exists || !lookup.data?.user_id) {
        Alert.alert('Not Registered', 'Please, Sign Up / Register First.');
        return;
      }
      const res = await api.post('/auth/biometric/verify-pin', { user_id: lookup.data.user_id, pin });
      if (res.data?.session_token) {
        await AsyncStorage.setItem('session_token', res.data.session_token);
        setCachedToken(res.data.session_token);
      } else {
        setCachedToken(null);
      }
      if (res.status === 200) {
        await refreshUser();
        await saveLastMethod('pin');
        redirectToApp();
      } else {
        Alert.alert('Login failed', 'Invalid PIN');
      }
    } catch (e: any) {
      Alert.alert('Login failed', e?.response?.data?.detail || 'Invalid PIN');
    }
  }, [email, refreshUser, redirectToApp, saveLastMethod]);

  const handlePasskeyLogin = useCallback(async () => {
    if (!isPasskeySupportedOnWeb()) {
      Alert.alert('Unavailable', 'Passkey login is currently supported on web browsers.');
      return;
    }
    try {
      const lookup = await api.get(`/auth/lookup?email=${encodeURIComponent(email)}`);
      if (!lookup.data?.exists || !lookup.data?.user_id) {
        Alert.alert('Not Registered', 'Please, Sign Up / Register First.');
        return;
      }
      const userId = lookup.data.user_id;
      const optRes = await api.post('/auth/biometric/webauthn-auth-options', { user_id: userId });
      const opts = normalizeAuthenticationOptions(optRes.data);
      const assertion = await (navigator as any).credentials.get({
        publicKey: {
          challenge: opts.challenge,
          allowCredentials: opts.allowCredentials,
          userVerification: 'required',
          timeout: opts.timeout,
        },
      }) as any;
      if (!assertion) {
        Alert.alert('Cancelled', 'Passkey login cancelled.');
        return;
      }
      const res = await api.post('/auth/biometric/webauthn-auth-complete', {
        user_id: userId,
        challenge_id: optRes.data?.challenge_id,
        credential: serializeWebAuthnCredential(assertion),
      });
      if (res.data?.session_token) {
        await AsyncStorage.setItem('session_token', res.data.session_token);
        setCachedToken(res.data.session_token);
      }
      setCachedToken(res.data?.session_token || null);
      await refreshUser();
      await saveLastMethod('passkey');
      redirectToApp();
    } catch (e: any) {
      if (e?.name === 'NotAllowedError') return;
      Alert.alert('Passkey login failed', e?.response?.data?.detail || 'Unable to login with passkey');
    }
  }, [email, refreshUser, redirectToApp, saveLastMethod]);

  return {
    show2FA,
    setShow2FA,
    otpCode,
    setOtpCode,
    otpHint,
    loginMethod,
    setLoginMethod,
    otpLoginCode,
    setOtpLoginCode,
    otpLoginHint,
    otpLoginRequested,
    otpLoginLoading,
    resending,
    setPendingAuthPassword,
    handleLogin,
    handleRequestOtp,
    handleOtpLogin,
    handleResendOTP,
    handle2FAVerify,
    handlePinLogin,
    handlePasskeyLogin,
  };
}
