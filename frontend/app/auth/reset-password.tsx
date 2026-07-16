import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

const staticColors = {
  error: '#EF4444', // @theme-ok brand/role/state identifier
  success: '#10B981', // @theme-ok brand/role/state identifier
};

export default function ResetPasswordScreen() {
  const { t } = useTranslation();
  t('i18n.route.auth.reset-password.probe');
  const router = useRouter();
  const { token } = useLocalSearchParams();
  const { colors } = useTheme();
  const [step, setStep] = useState('method');
  const [resetMethod, setResetMethod] = useState('email');
  const [email, setEmail] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [resetToken, setResetToken] = useState(null);

  const COLORS = useMemo(() => ({
    ...staticColors,
    primary: colors.primary,
    background: colors.bg,
    surface: colors.card,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  const styles = useMemo(() => createStyles(COLORS), [COLORS]);
  const tokenValue = useMemo(() => {
    if (Array.isArray(token)) return token[0];
    if (typeof token === 'string') return token;
    return null;
  }, [token]);

  useEffect(() => {
    if (tokenValue) {
      setResetToken(tokenValue);
      setStep('newPassword');
    }
  }, [tokenValue]);

  const handleSendCode = async () => {
    if (!email) {
      Alert.alert('Error', 'Please enter your email address');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/password/reset/request', { email });
      setStep('sent');
    } catch (error) {
      Alert.alert('Reset failed', error?.response?.data?.detail || 'Unable to send reset link.');
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async () => {
    if (newPassword.length < 8) {
      Alert.alert('Error', 'Password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }
    if (!resetToken) {
      Alert.alert('Invalid link', 'Please use the password reset link from your email.');
      return;
    }

    setLoading(true);
    try {
      await api.post('/auth/password/reset/confirm', { token: resetToken, new_password: newPassword });
      setStep('success');
    } catch (error) {
      Alert.alert('Reset failed', error?.response?.data?.detail || 'Unable to reset password.');
    } finally {
      setLoading(false);
    }
  };

  const renderMethodSelection = () => (
    <View style={styles.section} data-testid="reset-method-section" testID="reset-method-section">
      <View style={styles.iconContainer} data-testid="reset-method-icon" testID="reset-method-icon">
        <Ionicons name="lock-closed" size={48} color={COLORS.primary} />
      </View>
      <Text style={styles.title} data-testid="reset-method-title" testID="reset-method-title">{t("login.recovery.resetPassword")}</Text>
      <Text style={styles.subtitle} data-testid="reset-method-subtitle" testID="reset-method-subtitle">
        Choose how you’d like to reset your password
      </Text>

      <TouchableOpacity
        style={[styles.methodCard, resetMethod === 'email' && styles.methodCardSelected]}
        onPress={() => setResetMethod('email')}
        data-testid="reset-method-email" testID="reset-method-email"
      >
        <View style={[styles.methodIcon, { backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '15') }]} data-testid="reset-method-email-icon" testID="reset-method-email-icon">
          <Ionicons name="mail" size={24} color={COLORS.primary} />
        </View>
        <View style={styles.methodInfo}>
          <Text style={styles.methodTitle} data-testid="reset-method-email-title" testID="reset-method-email-title">Reset via Email</Text>
          <Text style={styles.methodDesc} data-testid="reset-method-email-desc" testID="reset-method-email-desc">We’ll email you a secure reset link</Text>
        </View>
        {resetMethod === 'email' && (
          <Ionicons name="checkmark-circle" size={24} color={COLORS.primary} />
        )}
      </TouchableOpacity>

      {/* Email input */}
      <View style={styles.inputContainer} data-testid="reset-email-input-container" testID="reset-email-input-container">
          <Text style={styles.inputLabel} data-testid="reset-email-label" testID="reset-email-label">{t("autofix.batch3.email.address")}</Text>
          <View style={styles.inputWrapper} data-testid="reset-email-input-wrapper" testID="reset-email-input-wrapper">
            <Ionicons name="mail-outline" size={20} color={COLORS.textMuted} />
            <TextInput
              style={styles.input}
              placeholder="Enter your email"
              placeholderTextColor={COLORS.textMuted}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              data-testid="reset-email-input" testID="reset-email-input"
            />
          </View>
        </View>

      <TouchableOpacity
        style={[styles.primaryButton, loading && styles.buttonDisabled]}
        onPress={handleSendCode}
        disabled={loading}
        data-testid="reset-send-link" testID="reset-send-link"
      >
        {loading ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.primaryButtonText}>{t("autofix.batch3.send.reset.link")}</Text>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderSent = () => (
    <View style={styles.section} data-testid="reset-sent-section" testID="reset-sent-section">
      <View style={styles.iconContainer} data-testid="reset-sent-icon" testID="reset-sent-icon">
        <Ionicons name="mail" size={48} color={COLORS.primary} />
      </View>
      <Text style={styles.title} data-testid="reset-sent-title" testID="reset-sent-title">{t("autofix.batch3.check.your.email")}</Text>
      <Text style={styles.subtitle} data-testid="reset-sent-subtitle" testID="reset-sent-subtitle">{t("autofix.batch3.we.sent.a.password.reset.link.to")}{email}{t("autofix.batch3.it.expires.in.30.minutes")}</Text>

      <TouchableOpacity
        style={styles.primaryButton}
        onPress={() => router.replace('/auth/login')}
        data-testid="reset-sent-back-login" testID="reset-sent-back-login"
      >
        <Text style={styles.primaryButtonText}>{t("autofix.batch3.back.to.login")}</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.resendButton} onPress={handleSendCode} data-testid="reset-sent-resend" testID="reset-sent-resend">
        <Text style={styles.resendText}>{t("autofix.batch3.didn.t.get.the.email")}</Text>
        <Text style={[styles.resendText, { color: COLORS.primary, fontWeight: '600' }]}>{t("autofix.batch3.resend.link")}</Text>
      </TouchableOpacity>
    </View>
  );

  const renderNewPassword = () => (
    <View style={styles.section} data-testid="reset-new-password-section" testID="reset-new-password-section">
      <View style={styles.iconContainer} data-testid="reset-new-password-icon" testID="reset-new-password-icon">
        <Ionicons name="key" size={48} color={COLORS.primary} />
      </View>
      <Text style={styles.title} data-testid="reset-new-password-title" testID="reset-new-password-title">Create New Password</Text>
      <Text style={styles.subtitle} data-testid="reset-new-password-subtitle" testID="reset-new-password-subtitle">
        Your new password must be at least 8 characters
      </Text>

      <View style={styles.inputContainer} data-testid="reset-new-password-input-container" testID="reset-new-password-input-container">
        <Text style={styles.inputLabel} data-testid="reset-new-password-label" testID="reset-new-password-label">New Password</Text>
        <View style={styles.inputWrapper} data-testid="reset-new-password-wrapper" testID="reset-new-password-wrapper">
          <Ionicons name="lock-closed-outline" size={20} color={COLORS.textMuted} />
          <TextInput
            style={styles.input}
            placeholder="Enter new password"
            placeholderTextColor={COLORS.textMuted}
            value={newPassword}
            onChangeText={setNewPassword}
            secureTextEntry={!showPassword}
            data-testid="reset-new-password-input" testID="reset-new-password-input"
          />
          <TouchableOpacity onPress={() => setShowPassword(!showPassword)} data-testid="reset-new-password-toggle" testID="reset-new-password-toggle">
            <Ionicons
              name={showPassword ? 'eye-off-outline' : 'eye-outline'}
              size={20}
              color={COLORS.textMuted}
            />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.inputContainer} data-testid="reset-confirm-password-container" testID="reset-confirm-password-container">
        <Text style={styles.inputLabel} data-testid="reset-confirm-password-label" testID="reset-confirm-password-label">Confirm Password</Text>
        <View style={styles.inputWrapper} data-testid="reset-confirm-password-wrapper" testID="reset-confirm-password-wrapper">
          <Ionicons name="lock-closed-outline" size={20} color={COLORS.textMuted} />
          <TextInput
            style={styles.input}
            placeholder="Confirm new password"
            placeholderTextColor={COLORS.textMuted}
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry={!showPassword}
            data-testid="reset-confirm-password-input" testID="reset-confirm-password-input"
          />
        </View>
      </View>

      <TouchableOpacity
        style={[styles.primaryButton, loading && styles.buttonDisabled]}
        onPress={handleResetPassword}
        disabled={loading}
        data-testid="reset-confirm-button" testID="reset-confirm-button"
      >
        {loading ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.primaryButtonText}>{t("login.recovery.resetPassword")}</Text>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderSuccess = () => (
    <View style={styles.section} data-testid="reset-success-section" testID="reset-success-section">
      <View style={[styles.iconContainer, { backgroundColor: (globalThis as any).__alphaColor(COLORS.success, '15') }]} data-testid="reset-success-icon" testID="reset-success-icon">
        <Ionicons name="checkmark-circle" size={64} color={COLORS.successText} />
      </View>
      <Text style={styles.title} data-testid="reset-success-title" testID="reset-success-title">Password Reset!</Text>
      <Text style={styles.subtitle} data-testid="reset-success-subtitle" testID="reset-success-subtitle">
        Your password has been successfully reset. You can now log in with your new password.
      </Text>

      <TouchableOpacity
        style={styles.primaryButton}
        onPress={() => router.replace('/auth/login?reset=success' as any)}
        data-testid="reset-success-login" testID="reset-success-login"
      >
        <Text style={styles.primaryButtonText}>{t("autofix.batch3.back.to.login")}</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} data-testid="reset-password-screen" testID="reset-password-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
        data-testid="reset-password-keyboard" testID="reset-password-keyboard"
      >
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.scrollContent}
          data-testid="reset-password-scroll" testID="reset-password-scroll"
        >
          {/* Header */}
          <View style={styles.header} data-testid="reset-password-header" testID="reset-password-header">
            <TouchableOpacity
              style={styles.backButton}
              onPress={() => {
                if (step === 'method') {
                  router.back();
                } else if (step === 'sent') {
                  setStep('method');
                } else if (step === 'newPassword') {
                  if (resetToken) {
                    router.replace('/auth/login');
                  } else {
                    setStep('method');
                  }
                } else if (step === 'success') {
                  router.replace('/auth/login');
                }
              }}
              data-testid="reset-password-back" testID="reset-password-back"
            >
              <Ionicons name="arrow-back" size={24} color={COLORS.text} />
            </TouchableOpacity>
            <Text style={styles.headerTitle} data-testid="reset-password-header-title" testID="reset-password-header-title">{t("login.recovery.resetPassword")}</Text>
            <View style={{ width: 24 }} />
          </View>

          {/* Content */}
          {step === 'method' && renderMethodSelection()}
          {step === 'sent' && renderSent()}
          {step === 'newPassword' && renderNewPassword()}
          {step === 'success' && renderSuccess()}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const createStyles = (COLORS) => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    flexGrow: 1,
    padding: 24,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  backButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  section: {
    flex: 1,
  },
  iconContainer: {
    width: 96,
    height: 96,
    borderRadius: 48,
    backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '15'),
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 28,
    fontWeight: '800',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 32,
  },
  methodCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    padding: 16,
    marginBottom: 12,
    borderWidth: 2,
    borderColor: COLORS.border,
  },
  methodCardSelected: {
    borderColor: COLORS.primary,
  },
  methodCardDisabled: {
    opacity: 0.6,
  },
  methodBadge: {
    backgroundColor: COLORS.border,
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  methodBadgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: COLORS.textMuted,
  },
  methodIcon: {
    width: 48,
    height: 48,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  methodInfo: {
    flex: 1,
    marginLeft: 12,
  },
  methodTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 2,
  },
  methodDesc: {
    fontSize: 13,
    color: COLORS.textMuted,
  },
  inputContainer: {
    marginTop: 24,
    marginBottom: 8,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: 8,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    paddingHorizontal: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  input: {
    flex: 1,
    paddingVertical: 16,
    marginLeft: 12,
    fontSize: 16,
    color: COLORS.text,
  },
  codeContainer: {
    alignItems: 'center',
    marginBottom: 24,
  },
  codeInput: {
    fontSize: 32,
    fontWeight: '700',
    color: COLORS.text,
    letterSpacing: 12,
    textAlign: 'center',
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    paddingVertical: 20,
    paddingHorizontal: 24,
    borderWidth: 1,
    borderColor: COLORS.border,
    width: '100%',
  },
  resendButton: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginBottom: 32,
  },
  resendText: {
    fontSize: 14,
    color: COLORS.textMuted,
  },
  primaryButton: {
    backgroundColor: COLORS.primary,
    borderRadius: 16,
    paddingVertical: 18,
    alignItems: 'center',
    marginTop: 24,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  primaryButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FEFEFE', // @theme-ok deliberate-high-contrast residual semantic hex (reviewed)
  },
});
