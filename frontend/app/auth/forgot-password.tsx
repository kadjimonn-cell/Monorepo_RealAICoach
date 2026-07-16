import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../../src/services/api';
import { useTheme } from '../../src/context/ThemeContext';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { useTranslation } from '../../src/hooks/useTranslation';

const staticColors = {
  error: '#EF4444', // @theme-ok brand/role/state identifier
  success: '#10B981', // @theme-ok brand/role/state identifier
};

export default function ForgotPasswordScreen() {
  const { t } = useTranslation();
  t('i18n.route.auth.forgot-password.probe');
  const router = useRouter();
  const { colors } = useTheme();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<'idle' | 'sent'>('idle');

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

  const handleSend = async () => {
    if (!email) {
      Alert.alert('Email required', 'Please enter your email address.');
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/password/reset/request', { email });
      setStatus('sent');
    } catch (error: any) {
      handleAppRecoverableError({
        scope: 'auth.forgot-password.send-reset-link',
        error,
        message: error?.response?.data?.detail || 'Unable to send reset link.',
        onRetry: () => { void handleSend(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Reset failed', error?.response?.data?.detail || 'Unable to send reset link.');
    } finally {
      setLoading(false);
    }
  };

  const renderSent = () => (
    <View style={styles.section} data-testid="forgot-password-sent-section" testID="forgot-password-sent-section">
      <View style={styles.iconContainer} data-testid="forgot-password-sent-icon" testID="forgot-password-sent-icon">
        <Ionicons name="mail" size={48} color={COLORS.primary} />
      </View>
      <Text style={styles.title} data-testid="forgot-password-sent-title" testID="forgot-password-sent-title">{t("autofix.batch3.check.your.email")}</Text>
      <Text style={styles.subtitle} data-testid="forgot-password-sent-subtitle" testID="forgot-password-sent-subtitle">{t("autofix.batch3.we.sent.a.password.reset.link.to")}{email}{t("autofix.batch3.it.expires.in.30.minutes")}</Text>

      <TouchableOpacity
        style={styles.primaryButton}
        onPress={() => router.replace('/auth/login')}
        data-testid="forgot-password-back-login" testID="forgot-password-back-login"
      >
        <Text style={styles.primaryButtonText}>{t("autofix.batch3.back.to.login")}</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.resendButton}
        onPress={handleSend}
        data-testid="forgot-password-resend" testID="forgot-password-resend"
      >
        <Text style={styles.resendText}>{t("autofix.batch3.didn.t.get.the.email")}</Text>
        <Text style={[styles.resendText, { color: COLORS.primary, fontWeight: '600' }]}>{t("autofix.batch3.resend.link")}</Text>
      </TouchableOpacity>
    </View>
  );

  return (
    <SafeAreaView style={styles.container} data-testid="forgot-password-screen" testID="forgot-password-screen">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
        data-testid="forgot-password-keyboard" testID="forgot-password-keyboard"
      >
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          data-testid="forgot-password-scroll" testID="forgot-password-scroll"
        >
          <View style={styles.header} data-testid="forgot-password-header" testID="forgot-password-header">
            <TouchableOpacity
              style={styles.backButton}
              onPress={() => router.back()}
              data-testid="forgot-password-back" testID="forgot-password-back"
            >
              <Ionicons name="arrow-back" size={24} color={COLORS.text} />
            </TouchableOpacity>
            <Text style={styles.headerTitle} data-testid="forgot-password-header-title" testID="forgot-password-header-title">Forgot Password</Text>
            <View style={{ width: 24 }} />
          </View>

          {status === 'sent' ? renderSent() : (
            <View style={styles.section} data-testid="forgot-password-form" testID="forgot-password-form">
              <View style={styles.iconContainer} data-testid="forgot-password-icon" testID="forgot-password-icon">
                <Ionicons name="lock-closed" size={48} color={COLORS.primary} />
              </View>
              <Text style={styles.title} data-testid="forgot-password-title" testID="forgot-password-title">Reset your password</Text>
              <Text style={styles.subtitle} data-testid="forgot-password-subtitle" testID="forgot-password-subtitle">
                Enter the email linked to your account and we’ll send a reset link.
              </Text>

              <View style={styles.inputContainer} data-testid="forgot-password-email-container" testID="forgot-password-email-container">
                <Text style={styles.inputLabel} data-testid="forgot-password-email-label" testID="forgot-password-email-label">{t("autofix.batch3.email.address")}</Text>
                <View style={styles.inputWrapper} data-testid="forgot-password-email-wrapper" testID="forgot-password-email-wrapper">
                  <Ionicons name="mail-outline" size={20} color={COLORS.textMuted} />
                  <TextInput
                    style={styles.input}
                    placeholder="Enter your email"
                    placeholderTextColor={COLORS.textMuted}
                    value={email}
                    onChangeText={setEmail}
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                    data-testid="forgot-password-email-input" testID="forgot-password-email-input"
                  />
                </View>
              </View>

              <TouchableOpacity
                style={[styles.primaryButton, loading && styles.buttonDisabled]}
                onPress={handleSend}
                disabled={loading}
                data-testid="forgot-password-send" testID="forgot-password-send"
              >
                {loading ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <Text style={styles.primaryButtonText}>{t("autofix.batch3.send.reset.link")}</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.secondaryButton}
                onPress={() => router.replace('/auth/login')}
                data-testid="forgot-password-back-login-secondary" testID="forgot-password-back-login-secondary"
              >
                <Text style={styles.secondaryButtonText}>{t("autofix.batch3.back.to.login")}</Text>
              </TouchableOpacity>
            </View>
          )}
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
  inputContainer: {
    marginBottom: 16,
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
  primaryButton: {
    backgroundColor: COLORS.primary,
    borderRadius: 16,
    paddingVertical: 18,
    alignItems: 'center',
    marginTop: 12,
  },
  primaryButtonText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#FEFEFE', // @theme-ok deliberate-high-contrast residual semantic hex (reviewed)
  },
  secondaryButton: {
    borderRadius: 16,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  secondaryButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: COLORS.text,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  resendButton: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 24,
  },
  resendText: {
    fontSize: 14,
    color: COLORS.textMuted,
  },
});
