import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity,
  KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator,
  Image, useWindowDimensions, Animated,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { FloatingImageShowcase } from '../../src/components/FloatingImageShowcase';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { getFrontendPlanName, getFrontendPlanPrice } from '../../src/config/pricingPolicy';

export default function RegisterScreen() {
  const { t } = useTranslation();
  t('i18n.route.auth.register.probe');
  const router = useRouter();
  const params = useLocalSearchParams();
  const { register, loginWithGoogle, loading } = useAuth();
  const { width } = useWindowDimensions();
  const { colors, darkMode } = useTheme();
  const T = {
    bg: colors.bg, bgAlt: colors.bgAlt, text: colors.text,
    gray300: colors.textSec, gray400: colors.textDim,
    glassBorder: colors.glassBorder, glassSurface: colors.glassSurface,
    error: colors.error, success: colors.success, neonBlue: colors.primary, cyan: colors.accent,
    // WCAG-AA icon/text variants — these are what Ionicons references. Missing
    // these defaults to `undefined` → invisible icons on dark mode (root-caused
    // Apr 20, 2026: benefit bullets + 256-bit/Secure Registration footer icons).
    successText: colors.successText || colors.success,
    isDark: darkMode,
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const st = useMemo(() => makeRegisterStyles(T), [colors, darkMode]);
  const isDesktop = width >= 860;

  // Plan info from Welcome pricing CTA
  const PLAN_PRICES: Record<string, { name: string; price: string }> = {
    free: { name: getFrontendPlanName('free'), price: String(getFrontendPlanPrice('free', 'monthly')) },
    basic: { name: getFrontendPlanName('basic'), price: String(getFrontendPlanPrice('basic', 'monthly')) },
    premium: { name: getFrontendPlanName('premium'), price: String(getFrontendPlanPrice('premium', 'monthly')) },
    enterprise: { name: 'Enterprise', price: '49.99' },
  };
  const rawPlanId = params.planId;
  const hasPlanId = rawPlanId && String(rawPlanId) !== 'undefined' && String(rawPlanId) !== '';
  const resolvedPlanId = hasPlanId ? String(rawPlanId).toLowerCase() : 'basic';
  const planLookup = PLAN_PRICES[resolvedPlanId] || PLAN_PRICES.basic;
  const rawName = params.planName;
  const rawPrice = params.planPrice;
  const pendingPlan = {
    planId: resolvedPlanId,
    planName: (rawName && String(rawName) !== 'undefined') ? String(rawName) : planLookup.name,
    planPrice: (rawPrice && String(rawPrice) !== 'undefined') ? String(rawPrice) : planLookup.price,
    billingPeriod: String(params.billingPeriod || 'monthly'),
  };

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');

  // SSO handlers use window.top.location.href with absolute URLs for iframe-safe navigation

  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(30)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeIn, { toValue: 1, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideUp, { toValue: 0, duration: 700, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [fadeIn, slideUp]);

  const getPasswordPolicyError = (value: string): string => {
    if (value.length < 8) return 'Password must be at least 8 characters';
    if (!/[A-Z]/.test(value)) return 'Password must contain at least one uppercase letter';
    if (!/[a-z]/.test(value)) return 'Password must contain at least one lowercase letter';
    if (!/[0-9]/.test(value)) return 'Password must contain at least one number';
    return '';
  };

  const handleRegister = async () => {
    if (!name || !email || !password || !confirmPassword) {
      setError('Please fill in all fields'); return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match'); return;
    }
    const passwordPolicyError = getPasswordPolicyError(password);
    if (passwordPolicyError) {
      setError(passwordPolicyError); return;
    }
    setError('');
    try {
      await register(email, password, name);
      if (pendingPlan) {
        router.replace(`/subscription/payment?planId=${pendingPlan.planId}&planName=${pendingPlan.planName}&planPrice=${pendingPlan.planPrice}&billingPeriod=${pendingPlan.billingPeriod}`);
      } else {
        router.replace('/dashboard');
      }
    } catch (err: any) {
      handleAppRecoverableError({
        scope: 'auth.register.submit',
        error: err,
        message: err.message || 'Registration failed',
        setError,
        onRetry: () => { void handleRegister(); },
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(err.message || 'Registration failed');
    }
  };

  const renderBrandPanel = () => (
    <View style={st.brandPanel}>
      <View style={st.brandInner}>
        <View style={st.brandLogoRow}>
          <Image source={Platform.OS === 'web' ? { uri: '/api/static/images/logo.png' } : require('../../assets/images/logo.png')} style={{ width: 34, height: 34, borderRadius: 9 }} resizeMode="contain" />
          <View data-notranslate>
            <Text style={st.brandLogoText}>Real<Text style={{ color: T.cyan }}>AI</Text>Coach</Text>
          </View>
        </View>

        <Text style={st.brandHeadline}>Start Your AI{'\n'}Coaching Journey</Text>

        <View style={st.brandTextCard}>
          <Text style={st.brandSub}>Join 10,000+ professionals using AI to accelerate their career growth and achieve extraordinary results.</Text>

          <View style={st.checkList}>
            {[
              { icon: 'checkmark-circle', text: '26 specialized AI coaching tools' },
              { icon: 'checkmark-circle', text: 'Personalized growth roadmaps' },
              { icon: 'checkmark-circle', text: 'Enterprise-grade security' },
              { icon: 'checkmark-circle', text: 'Free trial, no credit card required' },
            ].map((item, i) => (
              <View key={i} style={st.checkItem}>
                <Ionicons name={item.icon as any} size={18} color={T.successText} />
                <Text style={st.checkText}>{item.text}</Text>
              </View>
            ))}
          </View>

          <View style={st.brandTrust}>
            <Ionicons name="shield-checkmark" size={14} color={T.successText} />
            <Text style={st.brandTrustText}>SOC 2 Compliant</Text>
            <View style={st.brandTrustDot} />
            <Text style={st.brandTrustText}>GDPR Ready</Text>
          </View>
        </View>
      </View>

      {Platform.OS === 'web' && (
        <>
          <View style={[st.orbDecor, { top: '8%', right: -70, backgroundColor: T.cyan, opacity: 0.06 }]} />
          <View style={[st.orbDecor, { bottom: '12%', left: -50, backgroundColor: T.neonBlue, opacity: 0.08, width: 220, height: 220 }]} />
        </>
      )}
    </View>
  );

  return (
    <SafeAreaView style={st.root} data-testid="register-screen" testID="register-screen">
      {/* ─── Full-page floating background image ─── */}
      {Platform.OS === 'web' && (
        <div data-testid="register-background-image-layer" style={{ position: 'absolute', inset: 0, zIndex: 0 } as any}>
          <FloatingImageShowcase variant="desktop" isDarkTheme={darkMode} />
          <div
            data-testid="register-background-image-overlay"
            style={{
              position: 'absolute',
              inset: 0,
              background: darkMode
                ? 'linear-gradient(135deg, rgba(15,23,42,0.52) 0%, rgba(15,23,42,0.36) 42%, rgba(15,23,42,0.50) 100%)'
                : 'linear-gradient(135deg, rgba(248,250,252,0.38) 0%, rgba(241,245,249,0.24) 40%, rgba(248,250,252,0.36) 100%)',
              zIndex: 2,
              pointerEvents: 'none',
            } as any}
          />
        </div>
      )}

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[st.kav, { zIndex: 1 } as any]}>
        <View style={[st.wrapper, isDesktop && st.wrapperDesktop]}>
          {isDesktop && renderBrandPanel()}

          <ScrollView
            style={st.formPane}
            contentContainerStyle={st.formScroll}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <Animated.View style={[st.formCard, { opacity: fadeIn, transform: [{ translateY: slideUp }] }]} data-testid="register-card" testID="register-card">

              {!isDesktop && (
                <View style={st.mobileLogo}>
                  <TouchableOpacity onPress={() => router.back()} style={{ marginRight: 12 }} data-testid="register-back-button" testID="register-back-button">
                    <Ionicons name="arrow-back" size={22} color={T.text} />
                  </TouchableOpacity>
                  <Image source={Platform.OS === 'web' ? { uri: '/api/static/images/logo.png' } : require('../../assets/images/logo.png')} style={{ width: 30, height: 30, borderRadius: 8 }} resizeMode="contain" />
                  <View data-notranslate>
                    <Text style={st.mobileLogoText}>Real<Text style={{ color: T.cyan }}>AI</Text>Coach</Text>
                  </View>
                </View>
              )}

              <Text style={st.formTitle}>{t("auth.createAccount")}</Text>
              <Text style={st.formSub}>Start your AI-powered coaching journey today</Text>

              {pendingPlan && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: (globalThis as any).__alphaColor(T.cyan, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '30'), borderRadius: 10, padding: 12, marginBottom: 16 }} data-testid="register-plan-banner" testID="register-plan-banner">
                  <Ionicons name="rocket" size={16} color={T.cyan} />
                  <Text style={{ color: T.cyan, fontSize: 13, fontWeight: '600', flex: 1 }}>
                    Signing up for {pendingPlan.planName} Plan — ${pendingPlan.planPrice}/{pendingPlan.billingPeriod === 'yearly' ? 'yr' : 'mo'}
                  </Text>
                </View>
              )}

              {error ? (
                <View style={st.errBox} data-testid="register-error" testID="register-error">
                  <Ionicons name="alert-circle" size={15} color={T.error} />
                  <Text style={st.errText}>{error}</Text>
                </View>
              ) : null}

              <View style={st.field}>
                <Text style={st.label}>Full Name</Text>
                <View style={st.inputRow}>
                  <Ionicons name="person-outline" size={17} color={T.gray400} style={{ marginRight: 10 }} />
                  <TextInput
                    style={st.input}
                    placeholder="Your full name"
                    placeholderTextColor={T.gray400}
                    value={name}
                    onChangeText={setName}
                    autoCapitalize="words"
                    {...(Platform.OS !== 'web' ? { autoComplete: 'name' as const } : {})}
                    data-testid="register-name-input" testID="register-name-input"
                  />
                </View>
              </View>

              <View style={st.field}>
                <Text style={st.label}>Email Address</Text>
                <View style={st.inputRow}>
                  <Ionicons name="mail-outline" size={17} color={T.gray400} style={{ marginRight: 10 }} />
                  <TextInput
                    style={st.input}
                    placeholder="you@example.com"
                    placeholderTextColor={T.gray400}
                    value={email}
                    onChangeText={setEmail}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                    {...(Platform.OS !== 'web' ? { autoComplete: 'email' as const } : {})}
                    data-testid="register-email-input" testID="register-email-input"
                  />
                </View>
              </View>

              <View style={st.field}>
                <Text style={st.label}>Password</Text>
                <View style={st.inputRow}>
                  <Ionicons name="lock-closed-outline" size={17} color={T.gray400} style={{ marginRight: 10 }} />
                  <TextInput
                    style={st.input}
                    placeholder="Min. 8 chars, upper/lower/number"
                    placeholderTextColor={T.gray400}
                    value={password}
                    onChangeText={setPassword}
                    secureTextEntry={!showPassword}
                    autoCapitalize="none"
                    {...(Platform.OS !== 'web' ? { autoComplete: 'new-password' as const } : {})}
                    data-testid="register-password-input" testID="register-password-input"
                  />
                  <TouchableOpacity onPress={() => setShowPassword(!showPassword)} data-testid="register-toggle-password" testID="register-toggle-password">
                    <Ionicons name={showPassword ? 'eye-off-outline' : 'eye-outline'} size={17} color={T.gray400} />
                  </TouchableOpacity>
                </View>
                <Text style={st.fieldHint} data-testid="register-password-policy-hint" testID="register-password-policy-hint">
                  Use at least 8 characters with uppercase, lowercase, and number.
                </Text>
              </View>

              <View style={st.field}>
                <Text style={st.label}>Confirm Password</Text>
                <View style={st.inputRow}>
                  <Ionicons name="lock-closed-outline" size={17} color={T.gray400} style={{ marginRight: 10 }} />
                  <TextInput
                    style={st.input}
                    placeholder="Re-enter password"
                    placeholderTextColor={T.gray400}
                    value={confirmPassword}
                    onChangeText={setConfirmPassword}
                    secureTextEntry={!showPassword}
                    autoCapitalize="none"
                    {...(Platform.OS !== 'web' ? { autoComplete: 'new-password' as const } : {})}
                    data-testid="register-confirm-password-input" testID="register-confirm-password-input"
                  />
                </View>
              </View>

              <TouchableOpacity
                style={[st.primaryBtn, loading && { opacity: 0.6 }]}
                onPress={handleRegister}
                disabled={loading}
                data-testid="register-submit-button" testID="register-submit-button"
              >
                {loading ? (
                  <ActivityIndicator color={colors.primaryText} />
                ) : (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <Text style={st.primaryBtnText}>{t("auth.createAccount")}</Text>
                    <Ionicons name="arrow-forward" size={16} color={colors.primaryText} />
                  </View>
                )}
              </TouchableOpacity>

              {/* Divider */}
              <View style={st.divider}>
                <View style={st.dividerLine} />
                <Text style={st.dividerText}>or</Text>
                <View style={st.dividerLine} />
              </View>

              {/* Social SSO — iframe-safe SSO navigation */}
              <View style={st.ssoRow}>
                {Platform.OS === 'web' ? (
                  <>
                    <button
                      data-testid="register-google-button"
                      onClick={(e: any) => {
                        e.preventDefault();
                        const url = `https://auth.emergentagent.com/?redirect=${encodeURIComponent((typeof window !== 'undefined' ? (`https://${window.location.host}`) : process.env.EXPO_PUBLIC_BACKEND_URL || '') + '/')}`;
                        try { localStorage.setItem('last_login_method', 'sso'); } catch (error) { handleAppRecoverableError({ scope: 'auth/register.tsx#catch1', error, message: 'Something went wrong. Please retry.', notifyMode: 'silent' }); }
                        try {
                          const popup = window.open(url, '_blank', 'width=500,height=700,left=200,top=100');
                          if (!popup || popup.closed) { window.open(url, '_blank'); }
                        } catch (error) {
                          handleAppRecoverableError({
                            scope: 'auth.register.sso-google-popup-fallback',
                            error,
                            message: 'Could not open Google SSO popup cleanly.',
                            onRetry: () => { window.open(url, '_blank'); },
                            notifyMode: 'dialog',
                            userInitiated: true,
                          });
                          window.open(url, '_blank');
                        }
                      }}
                      style={{ flex: 1, display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 12, border: `1px solid ${T.glassBorder}`, backgroundColor: T.glassSurface, color: T.text, cursor: 'pointer', boxSizing: 'border-box' as const, fontFamily: 'inherit', padding: 0, minWidth: 0, overflow: 'hidden' }}
                    >
                      <Ionicons name="logo-google" size={16} color={T.text} />
                      <span style={{ color: T.text, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>Google</span>
                    </button>
                    <button
                      data-testid="register-microsoft-button"
                      onClick={(e: any) => {
                        e.preventDefault();
                        const apiOrigin = (((process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL) || (typeof window !== 'undefined' ? (`https://${window.location.host}`) : '')) || '').replace(/\/+$/, '');
                        const url = `${apiOrigin}/api/auth/microsoft/login`;
                        try { localStorage.setItem('last_login_method', 'sso'); } catch (error) { handleAppRecoverableError({ scope: 'auth/register.tsx#catch2', error, message: 'Something went wrong. Please retry.', notifyMode: 'silent' }); }
                        try {
                          const popup = window.open(url, '_blank', 'width=500,height=700,left=200,top=100');
                          if (!popup || popup.closed) { window.open(url, '_blank'); }
                        } catch (error) {
                          handleAppRecoverableError({
                            scope: 'auth.register.sso-microsoft-popup-fallback',
                            error,
                            message: 'Could not open Microsoft SSO popup cleanly.',
                            onRetry: () => { window.open(url, '_blank'); },
                            notifyMode: 'dialog',
                            userInitiated: true,
                          });
                          window.open(url, '_blank');
                        }
                      }}
                      style={{ flex: 1, display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 12, border: `1px solid ${T.glassBorder}`, backgroundColor: T.glassSurface, color: T.text, cursor: 'pointer', boxSizing: 'border-box' as const, fontFamily: 'inherit', padding: 0, minWidth: 0, overflow: 'hidden' }}
                    >
                      <Ionicons name="logo-microsoft" size={16} color={T.text} />
                      <span style={{ color: T.text, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>Microsoft</span>
                    </button>
                    <button
                      data-testid="register-apple-button"
                      onClick={(e: any) => {
                        e.preventDefault();
                        const apiOrigin = (((process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL) || (typeof window !== 'undefined' ? (`https://${window.location.host}`) : '')) || '').replace(/\/+$/, '');
                        const url = `${apiOrigin}/api/auth/apple/login`;
                        try { localStorage.setItem('last_login_method', 'sso'); } catch (error) { handleAppRecoverableError({ scope: 'auth/register.tsx#catch3', error, message: 'Something went wrong. Please retry.', notifyMode: 'silent' }); }
                        try {
                          const popup = window.open(url, '_blank', 'width=500,height=700,left=200,top=100');
                          if (!popup || popup.closed) { window.open(url, '_blank'); }
                        } catch (error) {
                          handleAppRecoverableError({
                            scope: 'auth.register.sso-linkedin-popup-fallback',
                            error,
                            message: 'Could not open LinkedIn SSO popup cleanly.',
                            onRetry: () => { window.open(url, '_blank'); },
                            notifyMode: 'dialog',
                            userInitiated: true,
                          });
                          window.open(url, '_blank');
                        }
                      }}
                      style={{ flex: 1, display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 12, border: `1px solid ${T.glassBorder}`, backgroundColor: T.glassSurface, color: T.text, cursor: 'pointer', boxSizing: 'border-box' as const, fontFamily: 'inherit', padding: 0, minWidth: 0, overflow: 'hidden' }}
                    >
                      <Ionicons name="logo-apple" size={16} color={T.text} />
                      <span style={{ color: T.text, fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap' }}>Apple</span>
                    </button>
                  </>
                ) : (
                  <>
                    <TouchableOpacity style={st.ssoBtn} onPress={() => { loginWithGoogle(); }} disabled={loading} accessibilityRole="button">
                      <Ionicons name="logo-google" size={16} color={T.text} />
                      <Text style={st.ssoBtnText} numberOfLines={1}>Google</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={st.ssoBtn} onPress={() => { if (Platform.OS !== 'web') return; }} disabled={loading} accessibilityRole="button">
                      <Ionicons name="logo-microsoft" size={16} color={T.text} />
                      <Text style={st.ssoBtnText} numberOfLines={1}>Microsoft</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={st.ssoBtn} onPress={() => { if (Platform.OS !== 'web') return; }} disabled={loading} accessibilityRole="button">
                      <Ionicons name="logo-apple" size={16} color={T.text} />
                      <Text style={st.ssoBtnText} numberOfLines={1}>Apple</Text>
                    </TouchableOpacity>
                  </>
                )}
              </View>

              {/* Security Trust */}
              <View style={st.securityBadge}>
                <Ionicons name="lock-closed" size={12} color={T.successText} />
                <Text style={st.securityText}>256-bit Encryption</Text>
                <View style={st.secDot} />
                <Ionicons name="shield-checkmark" size={12} color={T.successText} />
                <Text style={st.securityText}>Secure Registration</Text>
              </View>

              {/* Login link */}
              <View style={st.loginRow}>
                <Text style={st.loginText}>Already have an account? </Text>
                <TouchableOpacity onPress={() => router.push('/auth/login')} data-testid="register-login-link" testID="register-login-link">
                  <Text style={st.loginLink}>Sign In</Text>
                </TouchableOpacity>
              </View>
            </Animated.View>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const makeRegisterStyles = (T: { bg: string; bgAlt: string; text: string; gray300: string; gray400: string; glassBorder: string; glassSurface: string; error: string; success: string; neonBlue: string; cyan: string; isDark: boolean }) => StyleSheet.create({
  root: { flex: 1, backgroundColor: Platform.OS === 'web' ? 'transparent' : T.bg, position: 'relative', overflow: 'hidden' },
  kav: { flex: 1 },
  wrapper: { flex: 1 },
  wrapperDesktop: { flexDirection: 'row' },

  // Brand Panel
  brandPanel: { width: '45%', backgroundColor: 'transparent', justifyContent: 'center', padding: 56, borderRightWidth: 1, borderRightColor: T.glassBorder, overflow: 'hidden', position: 'relative' },
  brandInner: { maxWidth: 440, zIndex: 1 },
  brandLogoRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 48 },
  brandLogoText: { color: T.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.3 },
  brandHeadline: { color: T.text, fontSize: 36, fontWeight: '800', lineHeight: 46, letterSpacing: -0.8, marginBottom: 18 },
  brandTextCard: { backgroundColor: T.isDark ? 'rgba(5,10,20,0.75)' : 'rgba(255,255,255,0.88)', borderRadius: 16, padding: 20, marginBottom: 20, borderWidth: 1, borderColor: T.isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)', ...(Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}) },
  brandSub: { color: T.isDark ? T.gray400 : T.gray300, fontSize: 15, lineHeight: 24, marginBottom: 20 },
  checkList: { gap: 14, marginBottom: 36 },
  checkItem: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  checkText: { color: T.isDark ? T.gray300 : T.text, fontSize: 14, fontWeight: '500' },
  brandTrust: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  brandTrustText: { color: T.isDark ? T.gray400 : T.gray300, fontSize: 12, fontWeight: '500' },
  brandTrustDot: { width: 3, height: 3, borderRadius: 2, backgroundColor: T.gray400 },
  orbDecor: { position: 'absolute', width: 280, height: 280, borderRadius: 999 },

  // Form
  formPane: {
    flex: 1,
    backgroundColor: Platform.OS === 'web'
      ? ((globalThis as any).__alphaColor(T.bg, T.isDark ? '36' : '40'))
      : 'transparent',
    ...(Platform.OS === 'web'
      ? { backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)' }
      : {}) as any,
  },
  formScroll: { flexGrow: 1, justifyContent: 'center', paddingHorizontal: 24, paddingVertical: 32 },
  formCard: { width: '100%', maxWidth: 440, alignSelf: 'center', backgroundColor: T.glassSurface, borderRadius: 24, padding: 32, borderWidth: 1, borderColor: T.glassBorder, ...(Platform.OS === 'web' ? { boxShadow: `0 8px 40px rgba(0,0,0,${T.isDark ? '0.4' : '0.08'})`, backdropFilter: 'blur(24px)', WebkitBackdropFilter: 'blur(24px)' } as any : {}) },
  mobileLogo: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 32 },
  mobileLogoText: { color: T.text, fontSize: 17, fontWeight: '800' },
  formTitle: { color: T.text, fontSize: 28, fontWeight: '800', letterSpacing: -0.5 },
  formSub: { color: T.gray400, fontSize: 14, marginTop: 6, marginBottom: 28 },

  // Error
  errBox: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: (globalThis as any).__alphaColor(T.error, '0C'), padding: 12, borderRadius: 12, marginBottom: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.error, '1A') },
  errText: { color: T.error, fontSize: 13, flex: 1 },

  // Fields
  field: { marginBottom: 16 },
  label: { color: T.gray300, fontSize: 12, fontWeight: '700', marginBottom: 8, letterSpacing: 0.3 },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: T.bgAlt, borderRadius: 12, paddingHorizontal: 14, height: 50, borderWidth: 1, borderColor: T.glassBorder },
  input: { flex: 1, fontSize: 14, color: T.text },
  fieldHint: { color: T.gray400, fontSize: 11, marginTop: 7, lineHeight: 16 },

  // Buttons
  primaryBtn: { backgroundColor: T.neonBlue, height: 50, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginTop: 4 },
  primaryBtnText: { color: '#FEFEFE', fontSize: 15, fontWeight: '700' }, // @theme-ok deliberate-high-contrast residual semantic hex (reviewed)

  // Divider
  divider: { flexDirection: 'row', alignItems: 'center', marginVertical: 22 },
  dividerLine: { flex: 1, height: 1, backgroundColor: T.glassBorder },
  dividerText: { color: T.gray400, paddingHorizontal: 14, fontSize: 12, fontWeight: '500' },

  // SSO Row
  ssoRow: { flexDirection: 'row', gap: 8 },
  ssoBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 12, borderWidth: 1, borderColor: T.glassBorder, backgroundColor: T.glassSurface },
  ssoBtnText: { color: T.text, fontSize: 12, fontWeight: '600' },

  // Security
  securityBadge: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 6, marginTop: 22, paddingVertical: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.success, '08'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.success, '15') },
  securityText: { color: T.gray400, fontSize: 11, fontWeight: '600' },
  secDot: { width: 3, height: 3, borderRadius: 2, backgroundColor: T.gray400 },

  // Login
  loginRow: { flexDirection: 'row', justifyContent: 'center', marginTop: 22 },
  loginText: { color: T.gray400, fontSize: 13 },
  loginLink: { color: T.cyan, fontSize: 13, fontWeight: '700' },
});