import React from 'react';
import { ActivityIndicator, Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ProfileFormSkeleton } from '../../SkeletonLoaders';
import { SegmentedOtpInput } from './SegmentedOtpInput';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';
import { AUTH_QR_RENDER_CONTRACT } from './authQrContract';

const QRCode = React.lazy(() => import('react-qr-code'));

type LoginAuthMethodsPanelProps = {
  ctx: any;
};

export function LoginAuthMethodsPanel({ ctx }: LoginAuthMethodsPanelProps) {
  const {
    s, loginMethod, setLoginMethod, T, lastUsedMethod, tx, isTablet, isDesktop, focusedField, setFocusedField, email, setEmail, password, setPassword, showPassword, setShowPassword, router, pwStrength, rememberMe, setRememberMe, isBusy, handleLogin, colors, otpLoginLoading, handleRequestOtp, otpLoginRequested, otpLoginCode, setOtpLoginCode, otpLoginHint, handleOtpLogin, isInIframe, isUltraCompact, webOrigin, liveApiBase, startSsoDiagnostics, logSsoTelemetry, handleGoogleLogin, handleMicrosoftLogin, handleAppleLogin, loading, ssoDiagnostics, ssoProvider, cancelSsoDiagnostics, magicLinkSent, setMagicLinkSent, magicLinkLoading, setMagicLinkLoading, magicLinkEmail, setMagicLinkEmail, handleSendMagicLink, showQR, setShowQR, altMode, setAltMode, qrStatus, generateQR, pin, setPin, handlePinLogin, handlePasskeyLogin, qrUrl, showPasskeyEnrollmentPrompt, passkeyPromptBusy, handlePasskeyPromptDismiss, handlePasskeyPromptEnable, userHasPasskey, setUserHasPasskey, checkUserPasskeyEnrollment
  } = ctx;
  const [qrDiagnosticNotice, setQrDiagnosticNotice] = React.useState('');
  const qrDiagnosticTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const pushQrDiagnosticNotice = React.useCallback((message: string) => {
    setQrDiagnosticNotice(message);
    if (qrDiagnosticTimerRef.current) clearTimeout(qrDiagnosticTimerRef.current);
    qrDiagnosticTimerRef.current = setTimeout(() => {
      setQrDiagnosticNotice('');
      qrDiagnosticTimerRef.current = null;
    }, 2600);
  }, []);

  React.useEffect(() => {
    return () => {
      if (qrDiagnosticTimerRef.current) clearTimeout(qrDiagnosticTimerRef.current);
    };
  }, []);

  const handleOpenQrDiagnosticLink = React.useCallback(() => {
    if (!qrUrl || Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      const popup = window.open(qrUrl, '_blank', 'noopener,noreferrer');
      if (!popup || popup.closed) {
        window.location.assign(qrUrl);
      }
      pushQrDiagnosticNotice(tx('login.qrDiagnostics.opened', 'Approval link opened on this device.'));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/components/pages/login/LoginAuthMethodsPanel.tsx#openQrDiagnosticLink',
        error,
        message: tx('login.qrDiagnostics.openFailed', 'Unable to open the approval link right now.'),
        notifyMode: 'silent',
      });
      pushQrDiagnosticNotice(tx('login.qrDiagnostics.openFailed', 'Unable to open the approval link right now.'));
    }
  }, [pushQrDiagnosticNotice, qrUrl, tx]);

  const handleCopyQrDiagnosticLink = React.useCallback(async () => {
    if (!qrUrl || Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(qrUrl);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = qrUrl;
        textarea.setAttribute('readonly', 'true');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
      }
      pushQrDiagnosticNotice(tx('login.qrDiagnostics.copied', 'Approval link copied.'));
    } catch (error) {
      handleAppRecoverableError({
        scope: 'src/components/pages/login/LoginAuthMethodsPanel.tsx#copyQrDiagnosticLink',
        error,
        message: tx('login.qrDiagnostics.copyFailed', 'Unable to copy the approval link right now.'),
        notifyMode: 'silent',
      });
      pushQrDiagnosticNotice(tx('login.qrDiagnostics.copyFailed', 'Unable to copy the approval link right now.'));
    }
  }, [pushQrDiagnosticNotice, qrUrl, tx]);

  React.useEffect(() => {
    if (altMode !== 'passkey') return;
    if (typeof checkUserPasskeyEnrollment !== 'function') return;
    const typedEmail = String(email || '').trim();
    if (!typedEmail) {
      if (typeof setUserHasPasskey === 'function') setUserHasPasskey(null);
      return;
    }
    checkUserPasskeyEnrollment(typedEmail);
  }, [altMode, checkUserPasskeyEnrollment, email, setUserHasPasskey]);

  return (
    <>
      {showPasskeyEnrollmentPrompt && (
        <View
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(2,8,23,0.66)',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 120,
            paddingHorizontal: 16,
          }}
          data-testid="passkey-enrollment-overlay"
          testID="passkey-enrollment-overlay"
        >
          <View
            style={{
              width: '100%',
              maxWidth: 460,
              borderRadius: 16,
              borderWidth: 1,
              borderColor: T.glassBorder,
              backgroundColor: T.bgCard,
              padding: 18,
              gap: 10,
            }}
            data-testid="passkey-enrollment-modal"
            testID="passkey-enrollment-modal"
          >
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }} data-testid="passkey-enrollment-title" testID="passkey-enrollment-title">
              Would you like to use biometric login?
            </Text>
            <Text style={{ color: T.text2, fontSize: 13, lineHeight: 20 }} data-testid="passkey-enrollment-message" testID="passkey-enrollment-message">
              Use fingerprint/Face ID/Windows Hello for faster, phishing-resistant sign-in.
            </Text>
            <View style={{ flexDirection: 'row', gap: 10, justifyContent: 'flex-end', marginTop: 6 }}>
              <TouchableOpacity
                onPress={handlePasskeyPromptDismiss}
                disabled={passkeyPromptBusy}
                style={{
                  borderWidth: 1,
                  borderColor: T.glassBorder,
                  borderRadius: 10,
                  paddingHorizontal: 14,
                  paddingVertical: 10,
                  opacity: passkeyPromptBusy ? 0.7 : 1,
                }}
                data-testid="passkey-enrollment-not-now-button"
                testID="passkey-enrollment-not-now-button"
              >
                <Text style={{ color: T.text2, fontWeight: '600' }}>Not now</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={handlePasskeyPromptEnable}
                disabled={passkeyPromptBusy}
                style={{
                  borderRadius: 10,
                  paddingHorizontal: 14,
                  paddingVertical: 10,
                  backgroundColor: T.accent,
                  opacity: passkeyPromptBusy ? 0.7 : 1,
                }}
                data-testid="passkey-enrollment-enable-button"
                testID="passkey-enrollment-enable-button"
              >
                <Text style={{ color: T.white, fontWeight: '700' }}>Enable now</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

              {/* Method Tabs */}
              <View style={s.tabs} data-testid="login-method-tabs" testID="login-method-tabs">
                <TouchableOpacity
                  style={[s.tab, loginMethod === 'password' && s.tabActive]}
                  onPress={() => setLoginMethod('password')}
                  data-testid="login-method-password" testID="login-method-password"
                  accessibilityRole="button"
                >
                  <Ionicons name="lock-closed" size={13} color={loginMethod === 'password' ? T.white : T.text3} style={{ marginRight: 6 }} />
                  <Text style={[s.tabText, loginMethod === 'password' && s.tabTextActive]}>{tx('login.tabs.password', 'Password')}</Text>
                  {lastUsedMethod === 'password' && <View style={s.lastUsedDot} />}
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.tab, loginMethod === 'otp' && s.tabActive]}
                  onPress={() => setLoginMethod('otp')}
                  data-testid="login-method-otp" testID="login-method-otp"
                  accessibilityRole="button"
                >
                  <Ionicons name="mail" size={13} color={loginMethod === 'otp' ? T.white : T.text3} style={{ marginRight: 6 }} />
                  <Text style={[s.tabText, loginMethod === 'otp' && s.tabTextActive]}>{tx('login.tabs.oneTimeCode', 'One-Time Code')}</Text>
                  {lastUsedMethod === 'otp' && <View style={s.lastUsedDot} />}
                </TouchableOpacity>
              </View>

              {/* Email Field */}
              <View
                style={[
                  s.credentialsCluster,
                  isTablet && s.credentialsClusterTablet,
                  isDesktop && s.credentialsClusterDesktop,
                ]}
                data-testid="login-credentials-section" testID="login-credentials-section"
              >
              <View style={[s.field, s.credentialField]}>
                <Text style={s.label}>{tx('login.fields.email', 'EMAIL')}</Text>
                <View style={[s.inputRow, s.credentialInputRow, isTablet && s.credentialInputRowTablet, isDesktop && s.credentialInputRowDesktop, focusedField === 'email' && s.inputRowFocused]}>
                  <Ionicons name="mail-outline" size={17} color={focusedField === 'email' ? T.cyan : T.text3} style={{ marginRight: 10 }} />
                  <TextInput
                    className="login-input-web"
                    style={[s.input, s.credentialInput]}
                    placeholder={tx('login.fields.emailPlaceholder', 'you@example.com')}
                    placeholderTextColor={T.text3}
                    value={email}
                    onChangeText={setEmail}
                    onChange={(e: any) => {
                      const next = e?.nativeEvent?.text ?? e?.target?.value;
                      if (typeof next === 'string') setEmail(next);
                    }}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                    onFocus={() => setFocusedField('email')}
                    onBlur={() => setFocusedField('')}
                    data-testid="login-email-input" testID="login-email-input"
                    accessibilityLabel="Email address"
                  />
                </View>
              </View>

              {loginMethod === 'password' ? (
                <>
                  {/* Password Field */}
                  <View style={[s.field, s.credentialField]}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text style={s.label}>{tx('login.fields.password', 'PASSWORD')}</Text>
                      <TouchableOpacity onPress={() => router.push('/auth/forgot-password')} data-testid="login-forgot-password" testID="login-forgot-password">
                        <Text style={s.forgotLink}>{tx('login.fields.forgot', 'Forgot?')}</Text>
                      </TouchableOpacity>
                    </View>
                    <View style={[s.inputRow, s.credentialInputRow, isTablet && s.credentialInputRowTablet, isDesktop && s.credentialInputRowDesktop, focusedField === 'password' && s.inputRowFocused]}>
                      <Ionicons name="lock-closed-outline" size={17} color={focusedField === 'password' ? T.cyan : T.text3} style={{ marginRight: 10 }} />
                      <TextInput
                        className="login-input-web"
                        style={[s.input, s.credentialInput]}
                        placeholder={tx('login.fields.passwordPlaceholder', 'Enter password')}
                        placeholderTextColor={T.text3}
                        value={password}
                        onChangeText={setPassword}
                        onChange={(e: any) => {
                          const next = e?.nativeEvent?.text ?? e?.target?.value;
                          if (typeof next === 'string') setPassword(next);
                        }}
                        secureTextEntry={!showPassword}
                        autoCapitalize="none"
                        onFocus={() => setFocusedField('password')}
                        onBlur={() => setFocusedField('')}
                        data-testid="login-password-input" testID="login-password-input"
                        onSubmitEditing={handleLogin}
                        returnKeyType="go"
                        accessibilityLabel="Password"
                      />
                      <TouchableOpacity onPress={() => setShowPassword(!showPassword)} data-testid="login-toggle-password" testID="login-toggle-password" accessibilityRole="button">
                        <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={17} color={T.text3} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  {/* Password Strength */}
                  {password.length > 0 && (
                    <View style={s.strengthRow} data-testid="password-strength" testID="password-strength">
                      <View style={s.strengthTrack}>
                        {[1, 2, 3, 4].map(i => (
                          <View key={i} style={[s.strengthSeg, { backgroundColor: (globalThis as any).__alphaColor(i <= pwStrength.score ? pwStrength.color : T.text3, '30') }]} />
                        ))}
                      </View>
                      <Text style={[s.strengthLabel, { color: pwStrength.color }]}>{pwStrength.label}</Text>
                    </View>
                  )}

                  {/* Remember Me + Forgot Password */}
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 2, marginBottom: 4 }}>
                    <TouchableOpacity
                      onPress={() => setRememberMe(!rememberMe)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}
                      data-testid="remember-me-toggle" testID="remember-me-toggle"
                      accessibilityRole="checkbox"
                    >
                      <View style={{
                        width: 18, height: 18, borderRadius: 4,
                        borderWidth: 1.5,
                        borderColor: (globalThis as any).__alphaColor(rememberMe ? T.cyan : T.text3, '60'),
                        backgroundColor: rememberMe ? (globalThis as any).__alphaColor(T.cyan, '20') : 'transparent',
                        alignItems: 'center', justifyContent: 'center',
                      }}>
                        {rememberMe && <Ionicons name="checkmark" size={12} color={T.cyan} />}
                      </View>
                      <Text style={{ color: T.text3, fontSize: 12, fontWeight: '500' }}>{tx('login.rememberMe', 'Remember me on this device')}</Text>
                    </TouchableOpacity>
                  </View>

                  {/* Sign In Button */}
                  <TouchableOpacity className="login-btn-primary"
                    style={[s.primaryBtn, isBusy && { opacity: 0.6 }]}
                    onPress={handleLogin}
                    disabled={isBusy}
                    testID="login-submit-button"
                    data-testid="login-submit-button" 
                    accessibilityRole="button"
                    accessibilityLabel={tx('login.actions.signIn', 'Sign In')}
                  >
                    {isBusy ? <ActivityIndicator color={colors.primaryText} /> : (
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Text style={s.primaryBtnText}>{tx('login.actions.signInUpper', 'SIGN IN')}</Text>
                        <Ionicons name="arrow-forward" size={16} color={colors.primaryText} />
                      </View>
                    )}
                  </TouchableOpacity>
                </>
              ) : (
                <>
                  <TouchableOpacity
                    style={[s.secondaryBtn, otpLoginLoading && { opacity: 0.6 }]}
                    onPress={handleRequestOtp}
                    disabled={otpLoginLoading}
                    data-testid="login-otp-request" testID="login-otp-request"
                    accessibilityRole="button"
                  >
                    <Ionicons name="send" size={14} color={T.white} style={{ marginRight: 8 }} />
                    <Text style={s.secondaryBtnText}>{otpLoginLoading ? tx('login.actions.sending', 'Sending...') : otpLoginRequested ? tx('login.actions.resendCode', 'Resend Code') : tx('login.actions.sendCode', 'Send Code')}</Text>
                  </TouchableOpacity>
                  <View style={s.field}>
                    <Text style={s.label}>{tx('login.fields.verificationCode', 'VERIFICATION CODE')}</Text>
                    <SegmentedOtpInput
                      length={8}
                      value={otpLoginCode}
                      onChange={(val) => setOtpLoginCode(val)}
                      testIdPrefix="login-otp"
                      themeTokens={T}
                    />
                  </View>
                  {otpLoginHint ? <Text style={s.hintText} data-testid="login-otp-hint" testID="login-otp-hint">{otpLoginHint}</Text> : null}
                  <TouchableOpacity className="login-btn-primary" style={s.primaryBtn} onPress={handleOtpLogin} data-testid="login-otp-verify" testID="login-otp-verify" accessibilityRole="button">
                    <Text style={s.primaryBtnText}>{tx('login.actions.verifySignIn', 'VERIFY & SIGN IN')}</Text>
                  </TouchableOpacity>
                </>
              )}
              </View>

              {/* Divider */}
              <View style={s.divider}>
                <View style={s.dividerLine} />
                <Text style={s.dividerText}>{tx('login.common.or', 'OR')}</Text>
                <View style={s.dividerLine} />
              </View>

              {/* Social Auth — iframe-safe SSO navigation */}
              <>
              <View style={[s.socialRow, isUltraCompact && s.compactSocialRow]} data-testid="login-social-auth-row" testID="login-social-auth-row">
                {Platform.OS === 'web' && isInIframe ? (
                  /* ── IFRAME CONTEXT: Multi-strategy SSO ──
                     Strategy 1: Pure HTML <a target="_blank"> — browser-native navigation
                     Strategy 2: window.open() called in same click as backup
                     Strategy 3: If both fail after timeout, window.top.location.href redirect
                     Strategy 4: Magic Link email as final fallback */
                  <div style={{ display: 'flex', flexDirection: 'row' as const, gap: 8, width: '100%' }}>
                    {(() => {
                      const googleUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(webOrigin + '/')}`;
                      const msUrl = `${liveApiBase}/api/auth/microsoft/login`;
                      const appleUrl = `${liveApiBase}/api/auth/apple/login`;
                      const ssoOnClick = (url: string, name: string, provider: string) => (e: any) => {
                        // DO NOT preventDefault — let <a> tag navigation proceed as Strategy 1
                        startSsoDiagnostics(provider);
                        logSsoTelemetry(provider, 'click', { popup_method: 'anchor_click' });
                        try { localStorage.setItem('last_login_method', provider.toLowerCase()); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/LoginAuthMethodsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                        // Strategy 2: Also try window.open() in the same user gesture
                        try {
                          const popup = window.open(url, name, 'width=500,height=700,left=200,top=100');
                          if (popup && !popup.closed) {
                            logSsoTelemetry(provider, 'popup_opened', { popup_method: 'window_open_from_anchor' });
                            e.preventDefault(); // Popup worked — prevent <a> from also opening a tab
                          }
                        } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/LoginAuthMethodsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                      };
                      const btnStyle = (method: string) => ({
                        flex: 1, display: 'flex', flexDirection: 'row' as const, alignItems: 'center' as const, justifyContent: 'center' as const,
                        gap: 6, minHeight: isUltraCompact ? 44 : 48, borderRadius: 12, textDecoration: 'none' as const, cursor: 'pointer' as const,
                        border: `1.5px solid ${lastUsedMethod === method ? T.cyan + '50' : T.glassBorder}`,
                        backgroundColor: lastUsedMethod === method ? (globalThis as any).__alphaColor(T.cyan, '0A') : T.bgAlt,
                        boxSizing: 'border-box' as const,
                        width: '100%',
                      });
                      const btnTextColor = T.text;
                      return (<>
                        <button data-testid="login-google-button"
                          onClick={(e: any) => { ssoOnClick(googleUrl, 'sso_google', 'Google')(e); if (!e.defaultPrevented) window.open(googleUrl, '_blank'); }}
                          style={{...btnStyle('google'), fontFamily: 'inherit', padding: 0}}>
                          <Ionicons name="logo-google" size={16} color={btnTextColor} />
                          <span className="notranslate" data-notranslate translate="no" style={{ color: btnTextColor, fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>Google</span>
                        </button>
                        <button data-testid="login-microsoft-button"
                          onClick={(e: any) => { ssoOnClick(msUrl, 'sso_ms', 'Microsoft')(e); if (!e.defaultPrevented) window.open(msUrl, '_blank'); }}
                          style={{...btnStyle('microsoft'), fontFamily: 'inherit', padding: 0}}>
                          <Ionicons name="logo-microsoft" size={16} color={btnTextColor} />
                          <span className="notranslate" data-notranslate translate="no" style={{ color: btnTextColor, fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>Microsoft</span>
                        </button>
                        <button data-testid="login-apple-button"
                          onClick={(e: any) => { ssoOnClick(appleUrl, 'sso_apple', 'Apple')(e); if (!e.defaultPrevented) window.open(appleUrl, '_blank'); }}
                          style={{...btnStyle('apple'), fontFamily: 'inherit', padding: 0}}>
                          <Ionicons name="logo-apple" size={16} color={btnTextColor} />
                          <span className="notranslate" data-notranslate translate="no" style={{ color: btnTextColor, fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap' }}>Apple</span>
                        </button>
                      </>);
                    })()}
                  </div>
                ) : Platform.OS === 'web' ? (
                  <>
                    <TouchableOpacity
                      data-testid="login-google-button" testID="login-google-button"
                      onPress={handleGoogleLogin}
                      style={[{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: 0, height: 48, borderRadius: 12, borderWidth: 1, borderColor: lastUsedMethod === 'google' ? (globalThis as any).__alphaColor(T.cyan, '50') : T.glassBorder, backgroundColor: lastUsedMethod === 'google' ? (globalThis as any).__alphaColor(T.cyan, '0A') : T.bgAlt, position: 'relative', overflow: 'hidden' }, isUltraCompact && s.compactSocialButton]}
                    >
                      <Ionicons name="logo-google" size={16} color={T.white} />
                      <Text style={{ color: T.white, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>Google</Text>
                      {lastUsedMethod === 'google' && <View style={{ position: 'absolute', top: 2, right: 2, backgroundColor: T.cyan, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}><Text style={{ color: T.white, fontSize: 7, fontWeight: '800' }}>Last used</Text></View>}
                    </TouchableOpacity>
                    <TouchableOpacity
                      data-testid="login-microsoft-button" testID="login-microsoft-button"
                      onPress={handleMicrosoftLogin}
                      style={[{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: 0, height: 48, borderRadius: 12, borderWidth: 1, borderColor: lastUsedMethod === 'microsoft' ? (globalThis as any).__alphaColor(T.cyan, '50') : T.glassBorder, backgroundColor: lastUsedMethod === 'microsoft' ? (globalThis as any).__alphaColor(T.cyan, '0A') : T.bgAlt, position: 'relative', overflow: 'hidden' }, isUltraCompact && s.compactSocialButton]}
                    >
                      <Ionicons name="logo-microsoft" size={16} color={T.white} />
                      <Text style={{ color: T.white, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>Microsoft</Text>
                      {lastUsedMethod === 'microsoft' && <View style={{ position: 'absolute', top: 2, right: 2, backgroundColor: T.cyan, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}><Text style={{ color: T.white, fontSize: 7, fontWeight: '800' }}>Last used</Text></View>}
                    </TouchableOpacity>
                    <TouchableOpacity
                      data-testid="login-apple-button" testID="login-apple-button"
                      onPress={handleAppleLogin}
                      style={[{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, minWidth: 0, height: 48, borderRadius: 12, borderWidth: 1, borderColor: lastUsedMethod === 'apple' ? (globalThis as any).__alphaColor(T.cyan, '50') : T.glassBorder, backgroundColor: lastUsedMethod === 'apple' ? (globalThis as any).__alphaColor(T.cyan, '0A') : T.bgAlt, position: 'relative', overflow: 'hidden' }, isUltraCompact && s.compactSocialButton]}
                    >
                      <Ionicons name="logo-apple" size={16} color={T.white} />
                      <Text style={{ color: T.white, fontSize: 12, fontWeight: '600' }} numberOfLines={1}>Apple</Text>
                      {lastUsedMethod === 'apple' && <View style={{ position: 'absolute', top: 2, right: 2, backgroundColor: T.cyan, paddingHorizontal: 4, paddingVertical: 1, borderRadius: 3 }}><Text style={{ color: T.white, fontSize: 7, fontWeight: '800' }}>Last used</Text></View>}
                    </TouchableOpacity>
                  </>
                ) : (
                  <>
                    <TouchableOpacity style={[s.socialBtn, isUltraCompact && s.compactSocialButton, lastUsedMethod === 'google' && s.lastUsedSocialBtn]} onPress={handleGoogleLogin} disabled={loading} accessibilityRole="button" data-notranslate data-testid="login-google-button" testID="login-google-button">
                      <Ionicons name="logo-google" size={18} color={T.white} />
                      <Text style={s.socialBtnText} numberOfLines={1} data-notranslate>Google</Text>
                      {lastUsedMethod === 'google' && <Text style={s.lastUsedTag}>Last used</Text>}
                    </TouchableOpacity>
                    <TouchableOpacity style={[s.socialBtn, isUltraCompact && s.compactSocialButton, lastUsedMethod === 'microsoft' && s.lastUsedSocialBtn]} onPress={handleMicrosoftLogin} disabled={loading} accessibilityRole="button" data-notranslate data-testid="login-microsoft-button" testID="login-microsoft-button">
                      <Ionicons name="logo-microsoft" size={18} color={T.white} />
                      <Text style={s.socialBtnText} numberOfLines={1} data-notranslate>Microsoft</Text>
                      {lastUsedMethod === 'microsoft' && <Text style={s.lastUsedTag}>Last used</Text>}
                    </TouchableOpacity>
                    <TouchableOpacity style={[s.socialBtn, isUltraCompact && s.compactSocialButton, lastUsedMethod === 'apple' && s.lastUsedSocialBtn]} onPress={handleAppleLogin} disabled={loading} accessibilityRole="button" data-notranslate data-testid="login-apple-button" testID="login-apple-button">
                      <Ionicons name="logo-apple" size={18} color={T.white} />
                      <Text style={s.socialBtnText} numberOfLines={1} data-notranslate>Apple</Text>
                      {lastUsedMethod === 'apple' && <Text style={s.lastUsedTag}>Last used</Text>}
                    </TouchableOpacity>
                  </>
                )}
              </View>

              {/* SSO Diagnostics — auto-detects when SSO popup may have been blocked */}
              {ssoDiagnostics === 'waiting' && Platform.OS === 'web' && (
                <View style={{ marginTop: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '25'), backgroundColor: (globalThis as any).__alphaColor(T.cyan, '06'), flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="sso-diagnostics-waiting" testID="sso-diagnostics-waiting">
                  <ActivityIndicator size="small" color={T.cyan} />
                  <Text style={{ color: T.text2, fontSize: 12, flex: 1 }}>Waiting for {ssoProvider} sign-in to complete...</Text>
                  <TouchableOpacity onPress={cancelSsoDiagnostics} data-testid="sso-diagnostics-cancel" testID="sso-diagnostics-cancel">
                    <Ionicons name="close-circle-outline" size={16} color={T.text3} />
                  </TouchableOpacity>
                </View>
              )}

              {ssoDiagnostics === 'fallback' && Platform.OS === 'web' && (
                <View style={{ marginTop: 10, padding: 16, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.warning, '30'), backgroundColor: (globalThis as any).__alphaColor(T.warning, '06'), gap: 12 }} data-testid="sso-diagnostics-fallback" testID="sso-diagnostics-fallback">
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Ionicons name="warning-outline" size={18} color={T.warningText} />
                    <Text style={{ color: T.white, fontSize: 13, fontWeight: '700', flex: 1 }}>{ssoProvider} sign-in is taking longer than expected</Text>
                    <TouchableOpacity onPress={() => { cancelSsoDiagnostics(); setMagicLinkSent(false); }} data-testid="sso-diagnostics-dismiss" testID="sso-diagnostics-dismiss">
                      <Ionicons name="close" size={16} color={T.text3} />
                    </TouchableOpacity>
                  </View>
                  <Text style={{ color: T.text3, fontSize: 11, lineHeight: 16 }}>
                    The popup may have been blocked or the authentication didn&apos;t complete. Try one of these alternatives:
                  </Text>

                  {!magicLinkSent ? (
                    <View style={{ gap: 8 }}>
                      {/* Strategy 3: Redirect top-level window — bypasses ALL iframe restrictions */}
                      {Platform.OS === 'web' && isInIframe && (
                        <TouchableOpacity accessibilityLabel="Sso diagnostics redirect top button"
                          onPress={() => {
                            try {
                              const provider = ssoProvider.toLowerCase();
                              let url = '';
                              if (provider === 'google') url = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(webOrigin + '/')}`;
                              else if (provider === 'microsoft') url = `${liveApiBase}/api/auth/microsoft/login`;
                              else if (provider === 'apple') url = `${liveApiBase}/api/auth/apple/login`;
                              if (url) {
                                logSsoTelemetry(provider, 'direct_redirect', { popup_method: 'fallback_top_redirect' });
                                (window.top || window).location.href = url;
                              }
                            } catch {
                              logSsoTelemetry(ssoProvider.toLowerCase(), 'direct_redirect', { popup_method: 'fallback_location_href' });
                              try {
                                window.location.href = `${liveApiBase}/api/auth/${ssoProvider.toLowerCase()}/login`;
                              } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/login/LoginAuthMethodsPanel.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
                            }
                          }}
                          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 42, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.cyan, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '40') }}
                          data-testid="sso-diagnostics-redirect-top" testID="sso-diagnostics-redirect-top"
                        >
                          <Ionicons name="open-outline" size={14} color={T.cyan} />
                          <Text style={{ color: T.cyan, fontSize: 13, fontWeight: '700' }}>Open {ssoProvider} in Full Window</Text>
                        </TouchableOpacity>
                      )}

                      {/* Divider */}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 2 }}>
                        <View style={{ flex: 1, height: 1, backgroundColor: T.glassBorder }} />
                        <Text style={{ color: T.text3, fontSize: 10 }}>or use alternative</Text>
                        <View style={{ flex: 1, height: 1, backgroundColor: T.glassBorder }} />
                      </View>

                      {/* Magic Link option */}
                      <View style={{ gap: 6 }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', height: 40, borderRadius: 10, borderWidth: 1, borderColor: T.glassBorder, backgroundColor: T.bgAlt, paddingHorizontal: 12 }}>
                          <Ionicons name="mail-outline" size={14} color={T.text3} style={{ marginRight: 8 }} />
                          <TextInput
                            style={{ flex: 1, color: T.white, fontSize: 12, padding: 0, outlineStyle: 'none' } as any}
                            placeholder="Enter email for magic link"
                            placeholderTextColor={T.text3}
                            value={magicLinkEmail}
                            onChangeText={setMagicLinkEmail}
                            keyboardType="email-address"
                            autoCapitalize="none"
                            data-testid="sso-diagnostics-magic-email" testID="sso-diagnostics-magic-email"
                          />
                        </View>
                        <TouchableOpacity
                          onPress={handleSendMagicLink}
                          disabled={magicLinkLoading}
                          style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 38, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.neonBlue, '20'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.neonBlue, '40') }}
                          data-testid="sso-diagnostics-send-magic-link" testID="sso-diagnostics-send-magic-link"
                        >
                          {magicLinkLoading ? <ActivityIndicator size="small" color={T.neonBlue} /> : (
                            <>
                              <Ionicons name="link-outline" size={14} color={T.neonBlue} />
                              <Text style={{ color: T.neonBlue, fontSize: 12, fontWeight: '600' }}>Send Magic Link</Text>
                            </>
                          )}
                        </TouchableOpacity>
                      </View>

                      {/* Other fallback options */}
                      <View style={{ flexDirection: 'row', gap: 6 }}>
                        <TouchableOpacity
                          onPress={() => { cancelSsoDiagnostics(); setShowQR(true); setAltMode('none'); if (qrStatus === 'idle') generateQR(); }}
                          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.purple, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '30') }}
                          data-testid="sso-diagnostics-qr" testID="sso-diagnostics-qr"
                        >
                          <Ionicons name="qr-code-outline" size={13} color={T.purpleText} />
                          <Text style={{ color: T.purpleText, fontSize: 11, fontWeight: '600' }}>QR Code</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => { cancelSsoDiagnostics(); setLoginMethod('password'); setAltMode('none'); }}
                          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, height: 34, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(T.text3, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.text3, '30') }}
                          data-testid="sso-diagnostics-password" testID="sso-diagnostics-password"
                        >
                          <Ionicons name="lock-closed-outline" size={13} color={T.text2} />
                          <Text style={{ color: T.text2, fontSize: 11, fontWeight: '600' }}>Use Password</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ) : (
                    <View style={{ alignItems: 'center', gap: 8, padding: 8 }}>
                      <View style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: (globalThis as any).__alphaColor(T.success, '18'), justifyContent: 'center', alignItems: 'center' }}>
                        <Ionicons name="checkmark-circle" size={24} color={T.successText} />
                      </View>
                      <Text style={{ color: T.successText, fontSize: 13, fontWeight: '600' }}>Magic link sent!</Text>
                      <Text style={{ color: T.text3, fontSize: 11, textAlign: 'center', lineHeight: 16 }}>
                        Check your email for a one-click login link. It expires in 15 minutes.
                      </Text>
                      <TouchableOpacity
                        onPress={() => { setMagicLinkSent(false); setMagicLinkLoading(false); }}
                        style={{ marginTop: 4 }}
                        data-testid="sso-diagnostics-resend-magic" testID="sso-diagnostics-resend-magic"
                      >
                        <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '600' }}>Didn&apos;t receive it? Send again</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              )}

              {/* Quick Auth */}
              <View style={[s.quickRow, isUltraCompact && s.compactQuickRow]} data-testid="login-quick-auth-row" testID="login-quick-auth-row">
                <TouchableOpacity accessibilityLabel="Login pin mode button"
                  style={[s.quickBtn, isUltraCompact && s.compactQuickButton, altMode === 'pin' && s.quickBtnActive]}
                  onPress={() => { setAltMode(altMode === 'pin' ? 'none' : 'pin'); setShowQR(false); }}
                  disabled={loading}
                  data-testid="login-pin-mode" testID="login-pin-mode"
                  accessibilityRole="button"
                >
                  <Ionicons name="keypad" size={15} color={altMode === 'pin' ? T.cyan : T.text3} />
                  <Text style={[s.quickBtnText, altMode === 'pin' && { color: T.cyan }]}>PIN</Text>
                  {lastUsedMethod === 'pin' && <View style={s.lastUsedDot} />}
                </TouchableOpacity>
                <TouchableOpacity accessibilityLabel="Login passkey mode button"
                  style={[s.quickBtn, isUltraCompact && s.compactQuickButton, altMode === 'passkey' && { borderColor: (globalThis as any).__alphaColor(T.teal, '40'), backgroundColor: (globalThis as any).__alphaColor(T.teal, '08') }]}
                  onPress={() => { setAltMode(altMode === 'passkey' ? 'none' : 'passkey'); setShowQR(false); }}
                  disabled={loading}
                  data-testid="login-passkey-mode" testID="login-passkey-mode"
                  accessibilityRole="button"
                >
                  <Ionicons name="finger-print" size={15} color={altMode === 'passkey' ? T.teal : T.text3} />
                  <Text style={[s.quickBtnText, altMode === 'passkey' && { color: T.teal }]}>Passkey</Text>
                  {lastUsedMethod === 'passkey' && <View style={s.lastUsedDot} />}
                </TouchableOpacity>
                <TouchableOpacity
                    style={[s.quickBtn, isUltraCompact && s.compactQuickButton, showQR && { borderColor: (globalThis as any).__alphaColor(T.purple, '40'), backgroundColor: (globalThis as any).__alphaColor(T.purple, '08') }]}
                    onPress={() => { setShowQR(!showQR); setAltMode('none'); if (!showQR && qrStatus === 'idle') generateQR(); }}
                    disabled={loading}
                    data-testid="login-qr-mode" testID="login-qr-mode"
                    accessibilityRole="button"
                  >
                    <Ionicons name="qr-code-outline" size={15} color={showQR ? T.purple : T.text3} />
                    <Text style={[s.quickBtnText, showQR && { color: T.purpleText }]}>QR Login</Text>
                    {lastUsedMethod === 'qr' && <View style={s.lastUsedDot} />}
                </TouchableOpacity>
              </View>

              {altMode === 'pin' && (
                <View style={{ gap: 10, marginTop: 8 }}>
                  <View style={[s.inputRow, focusedField === 'pin' && s.inputRowFocused]} data-testid="login-pin-input-row" testID="login-pin-input-row">
                    <Ionicons name="lock-closed-outline" size={17} color={T.text3} style={{ marginRight: 10 }} />
                    <TextInput className="login-input-web" style={s.input} placeholder="4-digit PIN" placeholderTextColor={T.text3} value={pin} onChangeText={setPin} keyboardType="number-pad" maxLength={4} secureTextEntry data-testid="login-pin-input" testID="login-pin-input" onFocus={() => setFocusedField('pin')} onBlur={() => setFocusedField('')} />
                  </View>
                  <TouchableOpacity className="login-btn-primary" style={s.primaryBtn} onPress={handlePinLogin} disabled={loading} data-testid="login-pin-submit" testID="login-pin-submit" accessibilityRole="button">
                    <Text style={s.primaryBtnText}>SIGN IN WITH PIN</Text>
                  </TouchableOpacity>
                </View>
              )}

              {altMode === 'passkey' && (
                <>
                  {/* Only show passkey button if user has enrolled */}
                  {userHasPasskey && (
                    <TouchableOpacity className="login-btn-primary" style={[s.primaryBtn, { marginTop: 8 }]} onPress={handlePasskeyLogin} disabled={loading} data-testid="login-passkey-submit" testID="login-passkey-submit" accessibilityRole="button">
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                        <Ionicons name="finger-print" size={17} color={colors.primaryText} />
                        <Text style={s.primaryBtnText}>{Platform.OS === 'web' ? 'AUTHENTICATE WITH PASSKEY' : 'PASSKEY (WEB ONLY)'}</Text>
                      </View>
                    </TouchableOpacity>
                  )}
                  
                  {/* Show helper if no passkey enrolled */}
                  {userHasPasskey === false && (
                    <View
                      style={{ marginTop: 8, padding: 12, backgroundColor: colors.surface, borderRadius: 8, borderWidth: 1, borderColor: colors.border }}
                      data-testid="login-passkey-empty-state"
                      testID="login-passkey-empty-state"
                    >
                      <Text style={{ color: colors.textSecondary, fontSize: 13, textAlign: 'center' }} data-testid="login-passkey-empty-state-text" testID="login-passkey-empty-state-text">
                        💡 Enable Passkey login in Security Settings after signing in
                      </Text>
                    </View>
                  )}
                </>
              )}

              {/* QR Quick Login Panel */}
              {showQR && (
                <View style={{ marginTop: 12, alignItems: 'center', gap: 12, padding: 16, borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '30'), backgroundColor: (globalThis as any).__alphaColor(T.purple, '06') }} data-testid="qr-login-panel" testID="qr-login-panel">
                  {qrStatus === 'generating' && (
                    <ProfileFormSkeleton />
                  )}
                  {qrStatus === 'pending' && qrUrl && (
                    <>
                      <Text style={{ color: T.white, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>Scan with your phone</Text>
                      <Text style={{ color: T.text3, fontSize: 11, textAlign: 'center', lineHeight: 16 }}>Open your phone camera and scan this QR code. You must be logged in on your phone to approve.</Text>
                      <View
                        style={{
                          padding: AUTH_QR_RENDER_CONTRACT.quietZonePadding,
                          backgroundColor: AUTH_QR_RENDER_CONTRACT.backgroundColor,
                          borderRadius: AUTH_QR_RENDER_CONTRACT.borderRadius,
                          borderWidth: 1,
                          borderColor: 'rgba(15,23,42,0.08)',
                          shadowColor: 'rgba(15,23,42,0.12)',
                          shadowOpacity: 0.18,
                          shadowRadius: 16,
                          shadowOffset: { width: 0, height: 8 },
                        }}
                        data-testid="qr-code-display"
                        testID="qr-code-display"
                      >
                        <React.Suspense fallback={<ActivityIndicator size="small" />}>
                          <QRCode
                            value={qrUrl}
                            size={AUTH_QR_RENDER_CONTRACT.size}
                            level="M"
                            bgColor={AUTH_QR_RENDER_CONTRACT.backgroundColor}
                            fgColor={AUTH_QR_RENDER_CONTRACT.moduleColor}
                          />
                        </React.Suspense>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: T.purple }} />
                        <Text style={{ color: T.purpleText, fontSize: 10, fontWeight: '600' }}>Waiting for approval...</Text>
                      </View>
                      {Platform.OS === 'web' && (
                        <View
                          style={{
                            width: '100%',
                            gap: 10,
                            paddingTop: 4,
                            borderTopWidth: 1,
                            borderTopColor: (globalThis as any).__alphaColor(T.purple, '18'),
                          }}
                          data-testid="qr-diagnostic-panel"
                          testID="qr-diagnostic-panel"
                        >
                          <View style={{ gap: 4, alignItems: 'center' }}>
                            <Text style={{ color: T.text2, fontSize: 10, fontWeight: '700', letterSpacing: 0.4 }} data-testid="qr-diagnostic-label" testID="qr-diagnostic-label">
                              {tx('login.qrDiagnostics.label', 'SUPPORT / QA DIAGNOSTIC')}
                            </Text>
                            <Text style={{ color: T.text3, fontSize: 10, textAlign: 'center', lineHeight: 15 }} data-testid="qr-diagnostic-description" testID="qr-diagnostic-description">
                              {tx('login.qrDiagnostics.description', 'If scanning is blocked, open or copy the same approval link on this device for troubleshooting.')}
                            </Text>
                          </View>
                          <View style={{ flexDirection: isUltraCompact ? 'column' : 'row', gap: 8, width: '100%' }}>
                            <TouchableOpacity
                              onPress={handleOpenQrDiagnosticLink}
                              style={{
                                flex: 1,
                                minHeight: 38,
                                borderRadius: 10,
                                borderWidth: 1,
                                borderColor: (globalThis as any).__alphaColor(T.cyan, '36'),
                                backgroundColor: (globalThis as any).__alphaColor(T.cyan, '08'),
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexDirection: 'row',
                                gap: 6,
                              }}
                              data-testid="qr-diagnostic-open-link-button"
                              testID="qr-diagnostic-open-link-button"
                              accessibilityRole="button"
                            >
                              <Ionicons name="open-outline" size={14} color={T.cyan} />
                              <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '700' }}>{tx('login.qrDiagnostics.open', 'Open on this device')}</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              onPress={handleCopyQrDiagnosticLink}
                              style={{
                                flex: 1,
                                minHeight: 38,
                                borderRadius: 10,
                                borderWidth: 1,
                                borderColor: (globalThis as any).__alphaColor(T.text3, '26'),
                                backgroundColor: (globalThis as any).__alphaColor(T.text3, '10'),
                                alignItems: 'center',
                                justifyContent: 'center',
                                flexDirection: 'row',
                                gap: 6,
                              }}
                              data-testid="qr-diagnostic-copy-link-button"
                              testID="qr-diagnostic-copy-link-button"
                              accessibilityRole="button"
                            >
                              <Ionicons name="copy-outline" size={14} color={T.text2} />
                              <Text style={{ color: T.text2, fontSize: 11, fontWeight: '700' }}>{tx('login.qrDiagnostics.copy', 'Copy approval link')}</Text>
                            </TouchableOpacity>
                          </View>
                          {qrDiagnosticNotice ? (
                            <Text style={{ color: T.cyan, fontSize: 10, textAlign: 'center', fontWeight: '600' }} data-testid="qr-diagnostic-status" testID="qr-diagnostic-status">
                              {qrDiagnosticNotice}
                            </Text>
                          ) : null}
                        </View>
                      )}
                    </>
                  )}
                  {qrStatus === 'expired' && (
                    <View style={{ alignItems: 'center', gap: 8 }}>
                      <Ionicons name="time-outline" size={24} color={T.text3} />
                      <Text style={{ color: T.text2, fontSize: 12 }}>QR code expired</Text>
                      <TouchableOpacity onPress={generateQR} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '40') }} data-testid="qr-regenerate-btn" testID="qr-regenerate-btn">
                        <Text style={{ color: T.purpleText, fontSize: 12, fontWeight: '700' }}>Generate New</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                  {qrStatus === 'error' && (
                    <View style={{ alignItems: 'center', gap: 8 }}>
                      <Ionicons name="alert-circle" size={24} color={T.error} />
                      <Text style={{ color: T.text2, fontSize: 12 }}>Failed to generate QR code</Text>
                      <TouchableOpacity onPress={generateQR} style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.purple, '40') }} accessibilityLabel="Retry" data-testid="qr-retry-btn" testID="qr-retry-btn">
                        <Text style={{ color: T.purpleText, fontSize: 12, fontWeight: '700' }}>Retry</Text>
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              )}
              </>
    </>
  );
}

/* i18n-probe t('i18n.auto.probe') */
