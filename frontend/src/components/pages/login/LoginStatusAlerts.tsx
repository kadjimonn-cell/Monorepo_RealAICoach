import React, { useEffect, useState } from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type LoginStatusAlertsProps = { ctx: any };

export function LoginStatusAlerts({ ctx }: LoginStatusAlertsProps) {
  const {
    s, ssoErrorCode, colors, T, tx, SSO_ERROR_MESSAGES, lastUsedMethod, ssoCallbacks, setSsoErrorCode, setError, setLoginMethod, liveApiBase, openSsoFullWindow, router, postLogoutBanner, emitLogoutBannerTelemetry, setPostLogoutBanner, postRedirectedBanner, setPostRedirectedBanner, postResetBanner, setPostResetBanner, error, authRecovery, lockoutHelpText, formattedRecoveryCountdown
  } = ctx;

  const [forceProtectedBannerFromQuery, setForceProtectedBannerFromQuery] = useState(false);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setForceProtectedBannerFromQuery(false);
      return;
    }

    const supportedReasons = new Set(['unauthenticated', 'session_expired', 'origin_mismatch_recovered']);
    const resolveFromQuery = () => {
      try {
        const params = new URLSearchParams(window.location.search || '');
        const reason = String(params.get('auth_reason') || '').trim().toLowerCase();
        const returnTo = String(params.get('return_to') || '').trim();
        setForceProtectedBannerFromQuery(Boolean(returnTo) && supportedReasons.has(reason));
      } catch {
        setForceProtectedBannerFromQuery(false);
      }
    };

    // Expo web can settle query params shortly after first paint.
    resolveFromQuery();
    let ticks = 0;
    const settleInterval = setInterval(() => {
      resolveFromQuery();
      ticks += 1;
      if (ticks >= 10) {
        clearInterval(settleInterval);
      }
    }, 250);

    const onPopState = () => resolveFromQuery();
    window.addEventListener('popstate', onPopState);
    return () => {
      clearInterval(settleInterval);
      window.removeEventListener('popstate', onPopState);
    };
  }, []);

  const shouldShowProtectedBanner = false;

  return (
    <>
              {/* Error */}
              {ssoErrorCode ? (
                <View style={{ backgroundColor: colors.errorSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '44'), borderRadius: 14, padding: 16, marginBottom: 16, gap: 10 }} data-testid="sso-fallback-card" testID="sso-fallback-card">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="warning-outline" size={20} color={colors.warning} />
                    <Text style={{ color: T.white, fontSize: 15, fontWeight: '700' }}>{tx('login.sso.notCompleted', 'Sign-in didn\'t complete')}</Text>
                  </View>
                  <Text style={{ color: T.gray400, fontSize: 13, lineHeight: 19 }}>
                    {SSO_ERROR_MESSAGES[ssoErrorCode] || tx('login.sso.genericIssue', 'The external sign-in provider encountered an issue. This can happen if the service is temporarily unavailable.')}
                  </Text>
                  {(ssoErrorCode === 'invalid_request' || ssoErrorCode === 'token_failed') && (lastUsedMethod === 'microsoft' || lastUsedMethod === 'apple') && (
                    <View style={{ padding: 10, borderRadius: 10, backgroundColor: colors.infoSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.info, '44') }} data-testid="sso-fallback-callback-info" testID="sso-fallback-callback-info">
                      <Text style={{ color: colors.infoText, fontSize: 11, fontWeight: '700', marginBottom: 4 }}>{tx('login.sso.expectedCallback', 'Expected callback')}</Text>
                      <Text style={{ color: T.gray300, fontSize: 11, lineHeight: 16 }} selectable>
                        {lastUsedMethod === 'microsoft' ? (ssoCallbacks?.microsoft || tx('login.sso.loadingCallback', 'Loading callback…')) : (ssoCallbacks?.apple || tx('login.sso.loadingCallback', 'Loading callback…'))}
                      </Text>
                    </View>
                  )}
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
                    <TouchableOpacity
                      onPress={() => { setSsoErrorCode(null); setError(''); if (Platform.OS === 'web') { window.history.replaceState({}, '', window.location.pathname); } }}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: colors.bgSoft }}
                      data-testid="sso-fallback-dismiss" testID="sso-fallback-dismiss"
                    >
                      <Ionicons name="close-circle-outline" size={14} color={T.gray300} />
                      <Text style={{ color: T.gray300, fontSize: 12, fontWeight: '600' }}>{tx('login.common.dismiss', 'Dismiss')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => { setSsoErrorCode(null); setError(''); setLoginMethod('password'); if (Platform.OS === 'web') { window.history.replaceState({}, '', window.location.pathname); } }}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: colors.purpleSoft }}
                      data-testid="sso-fallback-password" testID="sso-fallback-password"
                    >
                      <Ionicons name="lock-closed-outline" size={14} color={colors.accent} />
                      <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '600' }}>{tx('login.sso.usePasswordInstead', 'Use password instead')}</Text>
                    </TouchableOpacity>
                    {Platform.OS === 'web' && (lastUsedMethod === 'microsoft' || lastUsedMethod === 'apple') && (
                      <TouchableOpacity accessibilityLabel="Sso fallback full window button"
                        onPress={() => {
                          const url = `${liveApiBase}/api/auth/${lastUsedMethod}/login`;
                          openSsoFullWindow(url, lastUsedMethod);
                        }}
                        style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: colors.infoSoft }}
                        data-testid="sso-fallback-full-window" testID="sso-fallback-full-window"
                      >
                        <Ionicons name="open-outline" size={14} color={colors.accent} />
                        <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '600' }}>{tx('login.sso.openInFullWindow', 'Open in full window')}</Text>
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity
                      onPress={() => { if (Platform.OS === 'web') { window.location.href = '/contact'; } else { router.push('/contact' as any); } }}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 7, paddingHorizontal: 12, borderRadius: 8, backgroundColor: colors.infoSoft }}
                      data-testid="sso-fallback-support" testID="sso-fallback-support"
                    >
                      <Ionicons name="chatbubble-ellipses-outline" size={14} color={colors.accent} />
                      <Text style={{ color: colors.accent, fontSize: 12, fontWeight: '600' }}>{tx('login.common.contactSupport', 'Contact support')}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              ) : postLogoutBanner ? (
                <View style={[s.resetSuccessBox, { backgroundColor: (globalThis as any).__alphaColor(T.cyan, '14'), borderColor: (globalThis as any).__alphaColor(T.cyan, '44') }]} data-testid="login-logout-success-banner" testID="login-logout-success-banner">
                  <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, flex: 1 }}>
                    <Ionicons name="shield-checkmark-outline" size={16} color={T.infoText} style={{ marginTop: 2 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={[s.resetSuccessTitle, { color: T.infoText }]}>{tx('login.logoutBanner.title', 'Signed out successfully')}</Text>
                      <Text style={[s.resetSuccessText, { color: T.text2 }]}>{tx('login.logoutBanner.subtitle', 'You can sign in again anytime.')}</Text>
                    </View>
                  </View>
                  <TouchableOpacity accessibilityLabel="Login logout success dismiss button"
                    onPress={() => {
                      emitLogoutBannerTelemetry('dismissed');
                      setPostLogoutBanner(false);
                    }}
                    data-testid="login-logout-success-dismiss"
                    testID="login-logout-success-dismiss"
                  >
                    <Ionicons name="close" size={16} color={T.text3} />
                  </TouchableOpacity>
                </View>
              ) : shouldShowProtectedBanner ? (
                <View style={[s.resetSuccessBox, { display: 'none', height: 0, opacity: 0, overflow: 'hidden', marginBottom: 0, paddingVertical: 0, backgroundColor: (globalThis as any).__alphaColor(T.warning, '12'), borderColor: (globalThis as any).__alphaColor(T.warning, '44') }]} data-testid="login-auth-required-banner" testID="login-auth-required-banner">
                  <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, flex: 1 }}>
                    <Ionicons name="information-circle-outline" size={16} color={T.warningText} style={{ marginTop: 2 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={[s.resetSuccessTitle, { color: T.warningText }]} data-testid="login-auth-required-banner-title" testID="login-auth-required-banner-title">Sign in required for that page</Text>
                      <Text style={[s.resetSuccessText, { color: T.text2 }]} data-testid="login-auth-required-banner-subtitle" testID="login-auth-required-banner-subtitle">You were redirected from a protected route. Sign in once to continue without repeated prompts.</Text>
                    </View>
                  </View>
                  <TouchableOpacity
                    onPress={() => setPostRedirectedBanner(false)}
                    data-testid="login-auth-required-banner-dismiss"
                    testID="login-auth-required-banner-dismiss"
                  >
                    <Ionicons name="close" size={16} color={T.text3} />
                  </TouchableOpacity>
                </View>
              ) : postResetBanner ? (
                <View style={s.resetSuccessBox} data-testid="login-reset-success-banner" testID="login-reset-success-banner">
                  <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, flex: 1 }}>
                    <Ionicons name="checkmark-circle" size={16} color={T.successText} style={{ marginTop: 2 }} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.resetSuccessTitle}>{tx('login.resetSuccess.title', 'Password updated — you can sign in now')}</Text>
                      <Text style={s.resetSuccessText}>{tx('login.resetSuccess.subtitle', 'Your recovery was successful, and the temporary countdown has been waived for this sign-in.')}</Text>
                    </View>
                  </View>
                  <TouchableOpacity onPress={() => setPostResetBanner(false)} data-testid="login-reset-success-dismiss" testID="login-reset-success-dismiss">
                    <Ionicons name="close" size={16} color={T.text3} />
                  </TouchableOpacity>
                </View>
              ) : error ? (
                <>
                  <View style={s.errBox} data-testid="login-error" testID="login-error">
                    <Ionicons name="alert-circle" size={15} color={T.error} />
                    <Text style={s.errText}>{error}</Text>
                  </View>
                  {authRecovery?.code ? (
                    <View style={s.recoveryBox} data-testid="login-recovery-box" testID="login-recovery-box">
                      <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8 }}>
                        <Ionicons name="shield-checkmark" size={15} color={T.cyan} style={{ marginTop: 2 }} />
                        <View style={{ flex: 1 }}>
                          <Text style={s.recoveryTitle}>{tx('login.recovery.title', 'Account recovery options')}</Text>
                          {lockoutHelpText ? <Text style={s.recoveryText}>{lockoutHelpText}</Text> : null}
                        {formattedRecoveryCountdown ? (
                          <View style={s.recoveryCountdownPill} data-testid="login-recovery-countdown" testID="login-recovery-countdown">
                            <Ionicons name="time-outline" size={12} color={T.cyan} />
                            <Text style={s.recoveryCountdownText}>{tx('login.recovery.tryAgainIn', 'Try again in {time}').replace('{time}', String(formattedRecoveryCountdown))}</Text>
                          </View>
                        ) : null}
                        </View>
                      </View>
                      <View style={s.recoveryActionsRow}>
                        <TouchableOpacity
                          onPress={() => router.push((authRecovery.resetPasswordUrl || '/auth/forgot-password') as any)}
                          style={s.recoveryPrimaryBtn}
                          data-testid="login-recovery-reset-password"
                          testID="login-recovery-reset-password"
                        >
                          <Text style={s.recoveryPrimaryBtnText}>{tx('login.recovery.resetPassword', 'Reset Password')}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity accessibilityLabel="Login recovery contact support button"
                          onPress={() => {
                            const supportTarget = authRecovery.supportUrl || 'mailto:security@realaicoach.app';
                            if (Platform.OS === 'web' && String(supportTarget).startsWith('mailto:')) {
                              window.location.href = supportTarget;
                              return;
                            }
                            router.push(supportTarget as any);
                          }}
                          style={s.recoverySecondaryBtn}
                          data-testid="login-recovery-contact-support"
                          testID="login-recovery-contact-support"
                        >
                          <Text style={s.recoverySecondaryBtnText}>{tx('login.recovery.contactSupport', 'Contact Support')}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : null}
                  {Array.isArray(authRecovery?.nextSteps) && authRecovery.nextSteps.length > 0 ? (
                    <View style={s.guidanceBox} data-testid="login-risk-guidance-box" testID="login-risk-guidance-box">
                      <Text style={s.guidanceTitle} data-testid="login-risk-guidance-title" testID="login-risk-guidance-title">
                        {tx('login.security.nextStepsTitle', 'Security steps to continue')}
                      </Text>
                      {authRecovery?.displayMessage ? (
                        <Text style={s.guidanceMessage} data-testid="login-risk-guidance-message" testID="login-risk-guidance-message">
                          {authRecovery.displayMessage}
                        </Text>
                      ) : null}
                      {authRecovery.nextSteps.map((step: string, idx: number) => (
                        <View key={`${step}-${idx}`} style={s.guidanceStepRow} data-testid={`login-risk-guidance-step-${idx}`} testID={`login-risk-guidance-step-${idx}`}>
                          <Text style={s.guidanceStepIndex}>{idx + 1}.</Text>
                          <Text style={s.guidanceStepText}>{step}</Text>
                        </View>
                      ))}
                      {authRecovery?.emailNotificationSent ? (
                        <Text style={s.guidanceEmailHint} data-testid="login-risk-guidance-email-hint" testID="login-risk-guidance-email-hint">
                          {tx('login.security.emailSentHint', 'We also sent these instructions to your email for reference.')}
                        </Text>
                      ) : null}
                      <View style={s.guidanceActionsRow}>
                        <TouchableOpacity accessibilityLabel="Login open id verification button"
                          onPress={() => {
                            const idvTarget = authRecovery?.idvAccessToken
                              ? `/id-checker?idv_token=${encodeURIComponent(authRecovery.idvAccessToken)}`
                              : '/id-checker';
                            if (Platform.OS === 'web') {
                              window.location.href = idvTarget;
                            } else {
                              router.push(idvTarget as any);
                            }
                          }}
                          style={s.guidancePrimaryBtn}
                          data-testid="login-open-id-verification-button"
                          testID="login-open-id-verification-button"
                        >
                          <Text style={s.guidancePrimaryBtnText}>{tx('login.security.openIdVerification', 'Open ID Verification')}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : null}
                </>
              ) : null}


    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
