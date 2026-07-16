import React, { useState, useEffect } from 'react';
import { View, Text, ActivityIndicator, Platform, useWindowDimensions, TextInput, TouchableOpacity, ScrollView } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { ProfileFormSkeleton } from '../src/components/SkeletonLoaders';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

const API_URL = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || '');

interface VerifyResult {
  verified: boolean;
  reason?: string;
  document_type?: string;
  document_number?: string;
  date?: string;
  amount?: number;
  plan?: string;
  issuer?: string;
}

export default function VerifyPage() {
  const { t } = useTranslation();
  t('i18n.route.verify.probe');
  const { colors, darkMode } = useTheme();
  const params = useLocalSearchParams<{ doc?: string; t?: string }>();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 768;
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [emailSent, setEmailSent] = useState(false);
  const [emailError, setEmailError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const q = new URLSearchParams();
        if (params.doc) q.set('doc', params.doc);
        if (params.t) q.set('t', params.t);
        const res = await fetch(`${API_URL}/api/payments/verify?${q.toString()}`);
        const data = await res.json();
        setResult(data);
      } catch {
        setResult({ verified: false, reason: 'Could not connect to verification server.' });
      } finally {
        setLoading(false);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSendEmail = async () => {
    if (!email.trim() || !email.includes('@')) { setEmailError('Enter a valid email address.'); return; }
    setSending(true); setEmailError('');
    try {
      const res = await fetch(`${API_URL}/api/payments/verify/send-email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({ doc: params.doc, t: params.t, email: email.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to send');
      setEmailSent(true);
    } catch (e: any) {
      setEmailError(e.message || 'Something went wrong.');
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <ProfileFormSkeleton />
    );
  }

  const verified = result?.verified === true;
  const C = {
    pageBg: darkMode ? colors.bg : colors.bgAlt,
    cardBg: darkMode ? colors.card : colors.card,
    cardBorder: darkMode ? (colors.borderMd || colors.border) : colors.border,
    text: colors.text,
    muted: colors.textMuted,
    detailBg: darkMode ? (colors.cardMuted || colors.surfaceElevated) : colors.card,
    detailBorder: darkMode ? (colors.border || colors.borderMd) : colors.border,
    detailLabel: darkMode ? colors.textSec : colors.textMuted,
    detailValue: darkMode ? colors.text : colors.text,
    trustText: darkMode ? colors.textMuted : colors.textMuted,
    inputBg: darkMode ? (colors.surface) : colors.card,
    inputText: darkMode ? colors.text : colors.text,
    inputPlaceholder: darkMode ? colors.textMuted : colors.textMuted,
  };

  const details = verified ? [
    { label: 'Document Type', value: result?.document_type, icon: 'document-text' as const },
    { label: 'Document No.', value: result?.document_number, icon: 'barcode' as const },
    { label: 'Date', value: result?.date, icon: 'calendar' as const },
    { label: 'Amount', value: result?.amount ? `$${result.amount.toFixed(2)} USD` : undefined, icon: 'cash' as const },
    { label: 'Plan', value: result?.plan, icon: 'layers' as const },
    { label: 'Issued By', value: result?.issuer, icon: 'business' as const },
  ].filter(r => r.value) : [];

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: C.pageBg }}
      contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 24, paddingBottom: 40 }}
      data-testid="verify-page" testID="verify-page"
    >
      <View style={{
        backgroundColor: C.cardBg, borderRadius: 20, padding: isDesktop ? 48 : 32,
        borderWidth: 1, borderColor: C.cardBorder,
        maxWidth: 520, width: '100%', alignItems: 'center',
        ...(Platform.OS === 'web' ? { boxShadow: '0 8px 32px rgba(0,0,0,0.08)' } : {}),
      }}>
        {/* Status Icon */}
        <View style={{
          width: 80, height: 80, borderRadius: 40, marginBottom: 20,
          backgroundColor: verified ? colors.success : colors.error,
          justifyContent: 'center', alignItems: 'center',
        }}>
          <Ionicons name={verified ? 'shield-checkmark' : 'close-circle'} size={40} color={colors.primaryText || colors.buttonText || colors.card} />
        </View>

        <Text style={{ fontSize: 22, fontWeight: '800', color: C.text, textAlign: 'center', marginBottom: 8 }} data-testid="verify-title" testID="verify-title">
          {verified ? 'Document Verified' : 'Verification Failed'}
        </Text>

        <Text style={{ fontSize: 14, color: C.muted, textAlign: 'center', lineHeight: 20, marginBottom: 24 }} data-testid="verify-subtitle" testID="verify-subtitle">
          {verified ? 'This document is authentic and was issued by RealAICoach.' : (result?.reason || 'This document could not be verified.')}
        </Text>

        {/* Verified Details */}
        {details.length > 0 && (
          <View style={{ width: '100%', backgroundColor: C.detailBg, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.detailBorder }} data-testid="verify-details" testID="verify-details">
            {details.map((row, i) => (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: i < details.length - 1 ? 1 : 0, borderBottomColor: C.detailBorder }}>
                <Ionicons name={row.icon} size={16} color={colors.info} />
                <Text style={{ color: C.detailLabel, fontSize: 12, fontWeight: '600', width: 100 }}>{row.label}</Text>
                <Text style={{ color: C.detailValue, fontSize: 13, fontWeight: '600', flex: 1 }}>{row.value}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Email Forward Section */}
        {verified && (
          <EmailForwardSection
            email={email}
            setEmail={setEmail}
            emailSent={emailSent}
            emailError={emailError}
            setEmailError={setEmailError}
            sending={sending}
            handleSendEmail={handleSendEmail}
            docType={result?.document_type}
          />
        )}

        {/* Trust Badge */}
        <View style={{
          flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 24,
          paddingVertical: 8, paddingHorizontal: 16,
          backgroundColor: verified ? '#F0FDF4' : '#FEF2F2', borderRadius: 20,
        }}>
          <Ionicons name={verified ? 'lock-closed' : 'warning'} size={14} color={verified ? colors.success : colors.error} />
          <Text style={{ fontSize: 11, fontWeight: '600', color: verified ? colors.success : colors.error }}>
            {verified ? 'Secured by RealAICoach' : 'Contact support if you believe this is an error'}
          </Text>
        </View>
      </View>

      <Text style={{ color: C.trustText, fontSize: 11, marginTop: 20, textAlign: 'center' }}>
        RealAICoach Document Verification System
      </Text>
    </ScrollView>
  );
}

function EmailForwardSection({ email, setEmail, emailSent, emailError, setEmailError, sending, handleSendEmail, docType }: any) {
  const { colors, darkMode } = useTheme();
  const C = {
    sectionBg: darkMode ? (colors.surfaceElevated || colors.card) : colors.card,
    sectionBorder: colors.border,
    heading: colors.text,
    body: colors.textMuted,
    inputBg: darkMode ? (colors.surface || colors.card) : colors.card,
    inputBorder: colors.border,
    inputText: colors.text,
    placeholder: colors.textMuted,
    successBg: colors.successSoft || colors.bgSoft,
    successBorder: colors.success,
  };
  if (emailSent) {
    return (
      <View style={{ width: '100%', marginTop: 20, backgroundColor: C.successBg, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.successBorder, alignItems: 'center' }} data-testid="verify-email-sent" testID="verify-email-sent">
        <Ionicons name="checkmark-circle" size={28} color={colors.success} />
        <Text style={{ fontSize: 14, fontWeight: '700', color: colors.successText, marginTop: 6 }}>Sent!</Text>
        <Text style={{ fontSize: 12, color: C.body, textAlign: 'center', marginTop: 4 }}>
          {'The ' + (docType?.toLowerCase() || 'document') + ' has been emailed to ' + email}
        </Text>
      </View>
    );
  }

  return (
    <View style={{ width: '100%', marginTop: 20, backgroundColor: C.sectionBg, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.sectionBorder }} data-testid="verify-email-section" testID="verify-email-section">
      <Text style={{ fontSize: 13, fontWeight: '700', color: C.heading, marginBottom: 10 }}>Forward to Email</Text>
      <View style={{ flexDirection: 'row', gap: 8 }}>
        <TextInput
          value={email}
          onChangeText={(v: string) => { setEmail(v); setEmailError(''); }}
          placeholder="accountant@example.com"
          placeholderTextColor={C.placeholder}
          keyboardType="email-address"
          autoCapitalize="none"
          style={{
            flex: 1, backgroundColor: C.inputBg, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10,
            fontSize: 13, color: C.inputText, borderWidth: 1, borderColor: emailError ? '#EF4444' : C.inputBorder,
          }}
          data-testid="verify-email-input" testID="verify-email-input"
        />
        <TouchableOpacity
          onPress={handleSendEmail}
          disabled={sending}
          style={{
            backgroundColor: colors.accent, borderRadius: 10, width: 44,
            justifyContent: 'center', alignItems: 'center', opacity: sending ? 0.7 : 1,
          }}
          data-testid="verify-send-btn" testID="verify-send-btn"
        >
          {sending ? <ActivityIndicator size="small" color={colors.primaryText || colors.buttonText || colors.card} /> : <Ionicons name="send" size={16} color={colors.primaryText || colors.buttonText || colors.card} />}
        </TouchableOpacity>
      </View>
      {emailError ? <Text style={{ color: colors.error, fontSize: 11, marginTop: 6 }} data-testid="verify-email-error" testID="verify-email-error">{emailError}</Text> : null}
    </View>
  );
}