/**
 * /privacy-request
 * ──────────────
 * Public GDPR/CCPA self-service entry point.
 * User enters email + picks Export or Delete → backend emails a signed link.
 */
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View, useWindowDimensions, ScrollView } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

export default function PrivacyRequest() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
  const { width } = useWindowDimensions();
  const isMobile = width < 640;
  const isTablet = width >= 640 && width < 1024;
  const isDesktop = width >= 1024;

  const [email, setEmail] = useState('');
  const [action, setAction] = useState<'export' | 'delete'>('export');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const clean = email.trim().toLowerCase();
    if (!clean.includes('@') || !clean.includes('.')) {
      setError(tx('privacyRequest.errors.invalidEmail', 'Please enter a valid email address.'));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/gdpr/request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ email: clean, action }),
      });
      if (!res.ok) throw new Error(await res.text());
      setSubmitted(true);
    } catch (error: any) {
      const message = tx('privacyRequest.errors.requestFailed', 'Request failed. Please try again.');
      handleAppRecoverableError({
        scope: 'privacy-request.submit',
        error,
        message,
        setError,
        onRetry: () => { void submit(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }, [email, action]);

  // Semantic V2 colours: teal primary, red for destructive delete, never legacy indigo.
  const PRIMARY = colors.primary;
  const PRIMARY_SOFT = `${colors.primary}14`;
  const DANGER = colors.error;
  const DANGER_SOFT = `${DANGER}14`;

  const pad = isMobile ? 16 : isTablet ? 24 : 32;

  const card = {
    backgroundColor: colors.card,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: isMobile ? 14 : 18,
    padding: isMobile ? 20 : isTablet ? 28 : 36,
    maxWidth: isDesktop ? 620 : isTablet ? 560 : 480,
    width: '100%' as const,
    shadowColor: colors.card, // @theme-ok shadow-color-semantic (matches features/index shadow convention)
    shadowOpacity: 0.06,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 2,
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ flexGrow: 1, alignItems: 'center', justifyContent: 'center', padding: pad, paddingVertical: pad * 2 }}
      data-testid="privacy-request-page" testID="privacy-request-page"
    >
      <View style={card} data-testid="privacy-request-card" testID="privacy-request-card">
        <TouchableOpacity
          onPress={() => router.back()}
          data-testid="privacy-request-back" testID="privacy-request-back"
          style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
          <Ionicons name="arrow-back" size={18} color={colors.textSec} />
          <Text style={{ color: colors.textSec, marginLeft: 6, fontSize: 14, fontWeight: '600' }}>{tx('privacyRequest.actions.back', 'Back')}</Text>
        </TouchableOpacity>

        <Text style={{ color: colors.text, fontSize: isMobile ? 22 : 28, fontWeight: '800', marginBottom: 8, letterSpacing: -0.5 }}>
          {tx('privacyRequest.page.title', 'Your Privacy, Your Choice')}
        </Text>
        <Text style={{ color: colors.textSec, fontSize: isMobile ? 13 : 14, lineHeight: isMobile ? 20 : 22, marginBottom: 24 }}>
          {tx('privacyRequest.page.subtitle', "Under GDPR/CCPA, you may export or permanently delete all data associated with your email across our contact, support, and feedback systems. We'll email you a verification link valid for 15 minutes.")}
        </Text>

        {submitted ? (
          <View data-testid="privacy-request-success" testID="privacy-request-success" style={{ padding: 16, backgroundColor: colors.successSoft, borderRadius: 12, borderWidth: 1, borderColor: `${colors.success}33` }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6 }}>
              <Ionicons name="mail-outline" size={20} color={colors.success} />
              <Text style={{ color: colors.text, marginLeft: 8, fontWeight: '700' }}>Check your inbox</Text>
            </View>
            <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20 }}>
              If an account exists for <Text style={{ fontWeight: '700', color: colors.text }}>{email}</Text>, we've sent a verification link. Click it within 15 minutes to complete your request.
            </Text>
          </View>
        ) : (
          <>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>Email address</Text>
            <TextInput
              data-testid="privacy-request-email" testID="privacy-request-email"
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              style={{
                borderWidth: 1, borderColor: colors.border, borderRadius: 10,
                paddingHorizontal: 14, paddingVertical: isMobile ? 12 : 14, color: colors.text,
                backgroundColor: colors.bgSoft || colors.bg, marginBottom: 20, fontSize: 15,
              }}
            />

            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>What would you like to do?</Text>
            <View style={{ flexDirection: isMobile ? 'column' : 'row', gap: 10, marginBottom: 20 }}>
              {(['export', 'delete'] as const).map((a) => {
                const selected = action === a;
                const tone = a === 'delete' ? DANGER : PRIMARY;
                const toneSoft = a === 'delete' ? DANGER_SOFT : PRIMARY_SOFT;
                return (
                  <TouchableOpacity
                    key={a}
                    onPress={() => setAction(a)}
                    data-testid={`privacy-request-action-${a}`} testID={`privacy-request-action-${a}`}
                    style={{
                      ...(isMobile ? { width: '100%' as const } : { flex: 1 }),
                      borderWidth: 1.5,
                      borderColor: selected ? tone : colors.border,
                      backgroundColor: selected ? toneSoft : 'transparent',
                      borderRadius: 12, padding: 14,
                    }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}>
                      <Ionicons name={a === 'export' ? 'download-outline' : 'trash-outline'} size={18} color={selected ? tone : colors.textSec} />
                      <Text style={{ color: colors.text, fontWeight: '700', marginLeft: 8, fontSize: 14 }}>
                        {a === 'export' ? 'Export my data' : 'Delete my data'}
                      </Text>
                    </View>
                    <Text style={{ color: colors.textSec, fontSize: 12, lineHeight: 18 }}>
                      {a === 'export' ? 'Download a JSON copy of everything we store.' : 'Permanently remove all records. This cannot be undone.'}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {error && (
              <View data-testid="privacy-request-error" testID="privacy-request-error" style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: `${DANGER}14`, borderWidth: 1, borderColor: `${DANGER}33`, borderRadius: 10, padding: 10, marginBottom: 12 }}>
                <Ionicons name="alert-circle-outline" size={16} color={DANGER} />
                <Text style={{ color: DANGER, fontSize: 13, marginLeft: 6, flex: 1 }}>{error}</Text>
              </View>
            )}

            <TouchableOpacity
              data-testid="privacy-request-submit" testID="privacy-request-submit"
              disabled={submitting || !email}
              onPress={submit}
              style={{
                backgroundColor: action === 'delete' ? DANGER : PRIMARY,
                paddingHorizontal: 18, paddingVertical: isMobile ? 13 : 15, borderRadius: 10,
                alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8,
                opacity: submitting || !email ? 0.55 : 1,
              }}>
              {submitting ? (
                <ActivityIndicator color={colors.primaryText} />
              ) : (
                <>
                  <Ionicons name={action === 'delete' ? 'trash-outline' : 'mail-outline'} size={16} color={colors.primaryText} />
                  <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 15, letterSpacing: 0.2 }}>
                    Send verification email
                  </Text>
                </>
              )}
            </TouchableOpacity>

            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 14, textAlign: 'center', lineHeight: 16 }}>
              256-bit TLS in transit · Audit-logged · Response within 15 minutes
            </Text>
          </>
        )}
      </View>
    </ScrollView>
  );
}
