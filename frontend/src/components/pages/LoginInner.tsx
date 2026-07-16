import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
  Image, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { FloatingImageShowcase } from '../FloatingImageShowcase';
import { blur } from './login/designTokens';
import { WebStyleInjector } from './login/WebStyleInjector';
import { IntelligencePanel } from './login/IntelligencePanel';
import { LoginAuthMethodsPanel } from './login/LoginAuthMethodsPanel';
import { LoginStatusAlerts } from './login/LoginStatusAlerts';
import { LoginTwoFactorModal } from './login/LoginTwoFactorModal';
import { useLoginController } from './login/useLoginController';
import { useTheme } from '../../context/ThemeContext';
import EnterpriseDisclaimerToken from '../tokens/EnterpriseDisclaimerToken';

/* ═══════════════════════════════════════════════════════════ */
/*  SEGMENTED 8-BOX OTP INPUT                                  */
/* ═══════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════ */
/*  LOGIN SCREEN                                               */
/* ═══════════════════════════════════════════════════════════ */

type LoginScreenProps = {
  forceCompactMode?: boolean;
};

export default function LoginScreen({ forceCompactMode = false }: LoginScreenProps) {
  const { darkMode, colors } = useTheme();

  // ── Hydration-safe mounting guard ──
  // Expo Web uses SSG (Static Site Generation). The server-rendered HTML may differ from
  // what the client renders (due to window, localStorage, iframe detection, etc.).
  // React Error #418 occurs on mismatch, which can crash the app in iframe contexts.
  // By deferring ALL rendering until after mount, server and client both render the same
  // loading state → no mismatch → no crash.
  const [clientReady, setClientReady] = useState(false);
  useEffect(() => { setClientReady(true); }, []);

  if (!clientReady) {
    const loaderBg = Platform.OS === 'web' ? ('var(--app-bg)' as any) : colors.bg;
    // Minimal loading state that matches for both server and client hydration
    return (
      <View style={{ flex: 1, backgroundColor: loaderBg, justifyContent: 'center', alignItems: 'center' }}>
        <ActivityIndicator size="large" color={colors.accent} />
      </View>
    );
  }

  return <LoginScreenContent forceCompactMode={forceCompactMode} />;
}

function LoginScreenContent({ forceCompactMode = false }: LoginScreenProps) {
  const {
    router, loading, colors, darkMode, T, s, webAssetBase, isDesktop, isTablet, isMobile, isCompactMobile, isUltraCompact, webOrigin, liveApiBase, tx, headingText, subheadingText, SSO_ERROR_MESSAGES, email, setEmail, password, setPassword, showPassword, setShowPassword, error, setError, authRecovery, ssoErrorCode, setSsoErrorCode, show2FA, setShow2FA, otpCode, setOtpCode, setPendingAuthPassword, otpHint, loginMethod, setLoginMethod, otpLoginCode, setOtpLoginCode, otpLoginHint, otpLoginRequested, otpLoginLoading, resending, rememberMe, setRememberMe, altMode, setAltMode, pin, setPin, userHasPasskey, setUserHasPasskey, checkUserPasskeyEnrollment, postLogoutBanner, setPostLogoutBanner, postRedirectedBanner, setPostRedirectedBanner, postResetBanner, setPostResetBanner, emitLogoutBannerTelemetry, lockoutHelpText, formattedRecoveryCountdown, localLoading, showSuccess, focusedField, setFocusedField, lastUsedMethod, ssoCallbacks, showQR, setShowQR, qrUrl, qrStatus, ssoDiagnostics, ssoProvider, magicLinkSent, setMagicLinkSent, magicLinkLoading, setMagicLinkLoading, magicLinkEmail, setMagicLinkEmail, isInIframe, isInCrossOriginIframe, logSsoTelemetry, redirectToApp, isBusy, pwStrength, fadeIn, slideUp, startSsoDiagnostics, cancelSsoDiagnostics, handleSendMagicLink, handleLogin, handleRequestOtp, handleOtpLogin, handleResendOTP, handle2FAVerify, handlePinLogin, handlePasskeyLogin, showPasskeyEnrollmentPrompt, passkeyPromptBusy, handlePasskeyPromptDismiss, handlePasskeyPromptEnable, openSsoFullWindow, handleGoogleLogin, generateQR, handleMicrosoftLogin, handleAppleLogin, setThemeMode
  } = useLoginController(forceCompactMode);

  /* ─── Success Overlay ─── */
  if (showSuccess) {
    return (
      <View style={[s.root, { justifyContent: 'center', alignItems: 'center' }]}>
        <WebStyleInjector />
        <View style={{ alignItems: 'center' }} data-testid="login-success-overlay" testID="login-success-overlay">
          <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: (globalThis as any).__alphaColor(T.success, '18'), justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: (globalThis as any).__alphaColor(T.success, '40') }} data-testid="login-success-icon" testID="login-success-icon">
            <Ionicons name="checkmark" size={36} color={T.successText} />
          </View>
          <Text style={{ color: T.white, fontSize: 22, fontWeight: '700', marginTop: 20 }} data-testid="login-success-title" testID="login-success-title">Welcome Back</Text>
          <Text style={{ color: T.text2, fontSize: 14, marginTop: 8 }} data-testid="login-success-subtitle" testID="login-success-subtitle">Redirecting to your dashboard...</Text>
        </View>
      </View>
    );
  }

  /* ─── Render ─── */
  return (
    <SafeAreaView style={s.root} data-testid="login-screen" testID="login-screen">
      <WebStyleInjector />

      {/* ─── Full-page floating background image ─── */}
      {Platform.OS === 'web' && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 0 }}>
          <FloatingImageShowcase variant={isDesktop ? 'desktop' : 'mobile-fullscreen'} />
          {/* Theme-adaptive overlay for readability */}
          <div style={{ position: 'absolute', inset: 0, background: darkMode
            ? (isDesktop
              ? 'linear-gradient(135deg, rgba(5,10,20,0.65) 0%, rgba(11,18,33,0.50) 40%, rgba(5,10,20,0.60) 100%)'
              : 'linear-gradient(180deg, rgba(5,10,20,0.35) 0%, rgba(5,10,20,0.30) 50%, rgba(5,10,20,0.50) 100%)')
            : (isDesktop
              ? 'linear-gradient(135deg, rgba(248,250,252,0.88) 0%, rgba(241,245,249,0.82) 40%, rgba(248,250,252,0.85) 100%)'
              : 'linear-gradient(180deg, rgba(248,250,252,0.75) 0%, rgba(248,250,252,0.70) 50%, rgba(248,250,252,0.80) 100%)'),
            zIndex: 2, pointerEvents: 'none' }} />
        </div>
      )}

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1, zIndex: 1 } as any}>
        <View style={[s.wrapper, isDesktop && s.wrapperDesktop]}>

          {/* ─── Left: Login Form ─── */}
          <ScrollView
            contentContainerStyle={[
              s.formScroll,
              isMobile && s.formScrollMobile,
              isCompactMobile && s.formScrollCompact,
              isDesktop && { justifyContent: 'center' },
            ]}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
            style={isDesktop ? { width: '42%' } : undefined}
          >
            {/* Background particles */}
            {Platform.OS === 'web' && (
              <>
                <div className="particle" style={{ position: 'absolute', top: '15%', left: '10%', width: 6, height: 6, borderRadius: 3, backgroundColor: T.cyan, opacity: 0.3, pointerEvents: 'none' as any }} />
                <div className="particle-2" style={{ position: 'absolute', top: '40%', right: '15%', width: 4, height: 4, borderRadius: 2, backgroundColor: T.purple, opacity: 0.25, pointerEvents: 'none' as any }} />
                <div className="particle-3" style={{ position: 'absolute', bottom: '25%', left: '20%', width: 8, height: 8, borderRadius: 4, backgroundColor: T.neonBlue, opacity: 0.2, pointerEvents: 'none' as any }} />
                <div className="particle" style={{ position: 'absolute', top: '60%', right: '8%', width: 5, height: 5, borderRadius: 3, backgroundColor: T.teal, opacity: 0.2, pointerEvents: 'none' as any, animationDelay: '2s' }} />
              </>
            )}

            <Animated.View
              className="login-glass-card"
              style={[
                s.glassCard,
                isTablet && s.glassCardTablet,
                isMobile && s.glassCardMobile,
                isCompactMobile && s.glassCardCompact,
                { opacity: fadeIn, transform: [{ translateY: slideUp }] },
                blur,
              ]}
              data-testid="login-card" testID="login-card"
            >
              {/* Logo + Theme Toggle */}
              <View style={[s.logoRow, { justifyContent: 'space-between' }]}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Image source={Platform.OS === 'web' ? { uri: webAssetBase ? `${webAssetBase}/api/static/images/logo.png` : '/api/static/images/logo.png' } : require('../../assets/images/logo.png')} style={{ width: 36, height: 36, borderRadius: 10 }} resizeMode="contain" accessibilityLabel="AI" data-testid="login-brand-logo" testID="login-brand-logo" />
                  <View data-notranslate>
                    <Text style={s.logoText} data-testid="login-brand-wordmark" testID="login-brand-wordmark">Real<Text style={{ color: T.cyan }}>AI</Text>Coach</Text>
                  </View>
                </View>
                <TouchableOpacity
                  onPress={() => setThemeMode(darkMode ? 'light' : 'dark')}
                  style={{ width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: T.glassBorder, backgroundColor: darkMode ? colors.glassBorder : colors.bgSoft }}
                  data-testid="login-theme-toggle" testID="login-theme-toggle"
                  accessibilityLabel={darkMode ? tx('login.theme.switchToLight', 'Switch to light mode') : tx('login.theme.switchToDark', 'Switch to dark mode')}
                >
                  <Ionicons name={darkMode ? 'sunny-outline' : 'moon-outline'} size={15} color={T.text2} />
                </TouchableOpacity>
              </View>

              <Text style={[s.heading, isMobile && s.headingMobile]} data-testid="login-heading" testID="login-heading">{headingText === 'login.heading' ? 'Welcome Back' : headingText}</Text>
              <Text style={[s.subheading, isMobile && s.subheadingMobile]} data-testid="login-subheading" testID="login-subheading">{subheadingText === 'login.subheading' ? 'Sign in to your AI coaching command center' : subheadingText}</Text>

              <View
                style={{ marginBottom: 14 }}
                data-testid="login-tenant-disclaimer-slot"
                testID="login-tenant-disclaimer-slot"
              >
                <EnterpriseDisclaimerToken
                  context="banner"
                  testIdPrefix="login-tenant-ai-disclaimer"
                  maxWidth={420}
                />
              </View>

              <LoginStatusAlerts
                ctx={{
                  s, ssoErrorCode, colors, T, tx, SSO_ERROR_MESSAGES, lastUsedMethod, ssoCallbacks, setSsoErrorCode, setError, setLoginMethod, liveApiBase, openSsoFullWindow, router, postLogoutBanner, emitLogoutBannerTelemetry, setPostLogoutBanner, postRedirectedBanner, setPostRedirectedBanner, postResetBanner, setPostResetBanner, error, authRecovery, lockoutHelpText, formattedRecoveryCountdown
                }}
              />

              <LoginAuthMethodsPanel
                ctx={{
                  s, loginMethod, setLoginMethod, T, lastUsedMethod, tx, isTablet, isDesktop, focusedField, setFocusedField, email, setEmail, password, setPassword, showPassword, setShowPassword, router, pwStrength, rememberMe, setRememberMe, isBusy, handleLogin, colors, otpLoginLoading, handleRequestOtp, otpLoginRequested, otpLoginCode, setOtpLoginCode, otpLoginHint, handleOtpLogin, isInIframe, isUltraCompact, webOrigin, liveApiBase, startSsoDiagnostics, logSsoTelemetry, handleGoogleLogin, handleMicrosoftLogin, handleAppleLogin, loading, ssoDiagnostics, ssoProvider, cancelSsoDiagnostics, magicLinkSent, setMagicLinkSent, magicLinkLoading, setMagicLinkLoading, magicLinkEmail, setMagicLinkEmail, handleSendMagicLink, showQR, setShowQR, altMode, setAltMode, qrStatus, generateQR, pin, setPin, handlePinLogin, handlePasskeyLogin, qrUrl, showPasskeyEnrollmentPrompt, passkeyPromptBusy, handlePasskeyPromptDismiss, handlePasskeyPromptEnable, userHasPasskey, setUserHasPasskey, checkUserPasskeyEnrollment
                }}
              />

              {/* Security Badge */}
              <View style={s.secBadge} data-testid="login-security-badge" testID="login-security-badge">
                <Ionicons name="lock-closed" size={11} color={T.successText} />
                <Text style={s.secText} data-testid="login-security-tls-text" testID="login-security-tls-text">256-bit TLS</Text>
                <View style={s.secDot} data-testid="login-security-dot" testID="login-security-dot" />
                <Ionicons name="shield-checkmark" size={11} color={T.successText} />
                <Text style={s.secText} data-testid="login-security-status-text" testID="login-security-status-text">Secure</Text>
              </View>

              {/* Register + Guest */}
              <View style={s.registerRow} data-testid="login-register-row" testID="login-register-row">
                <Text style={s.registerText} data-testid="login-register-label" testID="login-register-label">No account? </Text>
                <TouchableOpacity onPress={() => router.push('/auth/register')} data-testid="login-register-link" testID="login-register-link" accessibilityRole="link">
                  <Text style={s.registerLink} data-testid="login-register-link-text" testID="login-register-link-text">Create one</Text>
                </TouchableOpacity>
              </View>
            </Animated.View>
          </ScrollView>

          {/* ─── Right: Intelligence Panel (Desktop) ─── */}
          {isDesktop && <IntelligencePanel />}

          {/* ─── Mobile: Static Enterprise Badge ─── */}
          {isMobile && (
            <View style={s.mobileKpi}>
              {[
                { val: '99.9%', l: 'Uptime', c: T.cyan },
                { val: 'Live', l: 'AI Tools', c: T.purple },
                { val: '256-bit', l: 'Security', c: T.success },
              ].map((k, i) => (
                <View key={i} style={s.mobileKpiCard}>
                  <Text style={[s.mobileKpiVal, { color: k.c }]}>{k.val}</Text>
                  <Text style={s.mobileKpiLabel}>{k.l}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </KeyboardAvoidingView>

      <LoginTwoFactorModal
        ctx={{
          show2FA, s, blur, T, otpHint, tx, error, otpCode, setOtpCode, loading, colors, handle2FAVerify, handleResendOTP, resending, setShow2FA, setError, setPendingAuthPassword
        }}
      />

    </SafeAreaView>
  );
}

/* ═══════════════════════════════════════════════════════════ */
/*  STYLES                                                     */
/* ═══════════════════════════════════════════════════════════ */


/* i18n-probe t('i18n.auto.probe') */
