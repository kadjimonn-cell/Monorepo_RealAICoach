import { useCallback, useEffect, useMemo, useState } from 'react';

type UseLoginRecoveryParams = {
  initialError?: string;
  tx: (key: string, fallback: string) => string;
};

export function useLoginRecovery({ initialError = '', tx }: UseLoginRecoveryParams) {
  const [error, setError] = useState(initialError);
  const [authRecovery, setAuthRecovery] = useState<any>(null);
  const [recoveryCountdown, setRecoveryCountdown] = useState(0);

  const clearAuthIssue = useCallback(() => {
    setError('');
    setAuthRecovery(null);
    setRecoveryCountdown(0);
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
  }, [authRecovery, recoveryCountdown, tx]);

  const formattedRecoveryCountdown = useMemo(() => {
    if (!recoveryCountdown || recoveryCountdown <= 0) return '';
    const minutes = Math.floor(recoveryCountdown / 60);
    const seconds = recoveryCountdown % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }, [recoveryCountdown]);

  return {
    error,
    setError,
    authRecovery,
    setAuthRecovery,
    recoveryCountdown,
    setRecoveryCountdown,
    clearAuthIssue,
    handleAuthError,
    lockoutHelpText,
    formattedRecoveryCountdown,
  };
}
