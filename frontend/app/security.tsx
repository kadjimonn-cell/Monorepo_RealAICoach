import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, Alert, ActivityIndicator, Platform, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import AppShell from '../src/components/AppShell';
import { SecuritySettingsSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import api from '../src/services/api';
import { useTranslation } from '../src/hooks/useTranslation';
import {
  isPasskeySupportedOnWeb,
  normalizeRegistrationOptions,
  serializeWebAuthnCredential,
} from '../src/utils/webauthn';

import PublicPageShell from '../src/components/PublicPageLayout';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { TrustCenterTemplate } from '../src/components/legal/TrustCenterTemplate';

const statusColors = { green: '#10B981', red: '#EF4444', yellow: '#F59E0B', blue: '#0F766E' };
const SECURITY_HERO_IMAGE = 'https://images.unsplash.com/photo-1561233835-f937539b95b9?auto=format&fit=crop&w=1600&q=80';

/* ── Public Security Information Page ── */
function SecurityInfoPage() {
  const { colors: C, _darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const familyLinks = useMemo(() => [
    { id: 'privacy', label: tx('trustCenter.family.privacy', 'Privacy'), href: '/privacy-policy' },
    { id: 'terms', label: tx('trustCenter.family.terms', 'Terms'), href: '/terms' },
    { id: 'security', label: tx('trustCenter.family.security', 'Security'), href: '/security', active: true },
    { id: 'gdpr', label: tx('trustCenter.family.gdpr', 'GDPR'), href: '/gdpr' },
    { id: 'cookies', label: tx('trustCenter.family.cookies', 'Cookies'), href: '/cookies' },
  ], [tx]);

  const sections = useMemo(() => [
    {
      id: 'security-posture',
      icon: 'shield-checkmark-outline' as const,
      title: tx('securityCenter.section.posture.title', 'Security posture and platform model'),
      summary: tx('securityCenter.section.posture.summary', 'Explains how RealAICoach thinks about platform trust, resilience, access control, and operational defense.'),
      paragraphs: [
        tx('securityCenter.section.posture.p1', 'RealAICoach is built for users and teams who need visible guardrails around access, billing, privacy, and operational trust. Security is treated as a product layer, not an afterthought hidden in vendor jargon.'),
        tx('securityCenter.section.posture.p2', 'Our public security page is designed to help users evaluate our approach before they become paid users, and to support lightweight due-diligence conversations without requiring an enterprise sales workflow first.'),
      ],
      bullets: [
        tx('securityCenter.section.posture.b1', 'Security posture is tied to identity, route access, plan state, and operational monitoring'),
        tx('securityCenter.section.posture.b2', 'Public trust signals remain connected to privacy and GDPR rights surfaces'),
        tx('securityCenter.section.posture.b3', 'Controls are intended to be legible to both individuals and compliance reviewers'),
      ],
    },
    {
      id: 'encryption',
      icon: 'lock-closed-outline' as const,
      title: tx('securityCenter.section.encryption.title', 'Encryption, authentication, and access control'),
      summary: tx('securityCenter.section.encryption.summary', 'Core protections for credentials, sessions, transport, storage, and privileged access.'),
      paragraphs: [
        tx('securityCenter.section.encryption.p1', 'We use layered controls such as transport encryption, at-rest protection, role-based access, session controls, and provider-backed authentication flows to reduce unauthorized access risk.'),
        tx('securityCenter.section.encryption.p2', 'Authentication and access policy are linked to account state, entitlement controls, and security workflows rather than isolated login-only logic.'),
      ],
      facts: [
        { label: tx('securityCenter.table.encryption.transit', 'In transit'), value: tx('securityCenter.table.encryption.transitValue', 'TLS-protected browser and API traffic') },
        { label: tx('securityCenter.table.encryption.storage', 'At rest'), value: tx('securityCenter.table.encryption.storageValue', 'Encrypted storage, guarded secrets, and protected provider tokens') },
        { label: tx('securityCenter.table.encryption.access', 'Access control'), value: tx('securityCenter.table.encryption.accessValue', 'Session, role, and route-access enforcement with monitoring') },
      ],
    },
    {
      id: 'operations',
      icon: 'pulse-outline' as const,
      title: tx('securityCenter.section.operations.title', 'Monitoring, incident response, and platform operations'),
      summary: tx('securityCenter.section.operations.summary', 'We use layered monitoring and operational response patterns to detect issues and recover quickly.'),
      paragraphs: [
        tx('securityCenter.section.operations.p1', 'Monitoring, alerting, performance checks, route-health controls, and audit visibility all contribute to our security posture. Security is linked to reliability because silent product failure is also a trust issue.'),
        tx('securityCenter.section.operations.p2', 'When incidents happen, we aim for documented response, operational containment, and transparent recovery practices rather than vague blanket assurances.'),
      ],
      bullets: [
        tx('securityCenter.section.operations.b1', 'Operational monitoring and alerting support early issue detection'),
        tx('securityCenter.section.operations.b2', 'Incident workflows support containment, recovery, and review'),
        tx('securityCenter.section.operations.b3', 'Security and privacy surfaces remain linked for user trust continuity'),
      ],
    },
    {
      id: 'compliance',
      icon: 'document-text-outline' as const,
      title: tx('securityCenter.section.compliance.title', 'Compliance, privacy, and user controls'),
      summary: tx('securityCenter.section.compliance.summary', 'Security posture is strongest when privacy rights, legal transparency, and operational controls stay connected.'),
      paragraphs: [
        tx('securityCenter.section.compliance.p1', 'Our security posture connects to privacy, GDPR, account protection, and legal notice workflows so users are not forced to treat these as disconnected promises.'),
        tx('securityCenter.section.compliance.p2', 'This means public trust pages, privacy request actions, and policy update communications can reinforce one another instead of drifting apart over time.'),
      ],
      facts: [
        { label: tx('securityCenter.table.compliance.privacy', 'Privacy linkage'), value: tx('securityCenter.table.compliance.privacyValue', 'Manage-data and privacy rights pathways remain visible') },
        { label: tx('securityCenter.table.compliance.gdpr', 'GDPR linkage'), value: tx('securityCenter.table.compliance.gdprValue', 'GDPR rights and transfer language connect to this security posture') },
        { label: tx('securityCenter.table.compliance.updates', 'Legal notice continuity'), value: tx('securityCenter.table.compliance.updatesValue', 'Policy and trust updates can be communicated through aligned product/email channels') },
      ],
    },
  ], [tx]);

  return (
    <PublicPageShell maxWidth={1320}>
      <TrustCenterTemplate
        testIdPrefix="security-center"
        heroImage={SECURITY_HERO_IMAGE}
        heroImageAlt={tx('securityCenter.hero.imageAlt', 'Abstract security infrastructure background')}
        badge={tx('securityCenter.hero.badge', 'SECURITY TRUST CENTER')}
        version={tx('securityCenter.hero.version', 'Version 2026.2')}
        title={tx('securityCenter.hero.title', 'Security posture that users can understand before they trust us with work.')}
        subtitle={tx('securityCenter.hero.subtitle', 'This page turns platform security, reliability, incident readiness, and trust controls into a readable product-grade security experience.')}
        metaItems={[
          tx('securityCenter.hero.meta.updated', 'Last updated: March 20, 2026'),
          tx('securityCenter.hero.meta.response', 'Operational incident workflows support rapid detection and recovery'),
          tx('securityCenter.hero.meta.linkage', 'Linked to Privacy and GDPR trust surfaces'),
        ]}
        heroPrimaryCta={{ label: tx('securityCenter.hero.cta.contact', 'Contact Security & Support'), href: '/help', testId: 'security-center-contact-cta' }}
        heroSecondaryCta={{ label: tx('securityCenter.hero.cta.privacy', 'Review Privacy Commitments'), href: '/privacy-policy', testId: 'security-center-privacy-cta' }}
        familyLinks={familyLinks}
        summaryTitle={tx('securityCenter.summary.title', 'TL;DR — the trust posture behind the platform')}
        trustFacts={[
          { id: 'identity', title: tx('securityCenter.fact.identity.title', 'Identity & access'), body: tx('securityCenter.fact.identity.body', 'Authentication, route-access, and account-state controls work together.'), icon: 'finger-print-outline' },
          { id: 'encryption', title: tx('securityCenter.fact.encryption.title', 'Encryption layers'), body: tx('securityCenter.fact.encryption.body', 'Transport, storage, and token handling protections support sensitive workflows.'), icon: 'lock-closed-outline' },
          { id: 'operations', title: tx('securityCenter.fact.operations.title', 'Operational defense'), body: tx('securityCenter.fact.operations.body', 'Monitoring, response, and recovery practices reinforce user trust.'), icon: 'pulse-outline' },
          { id: 'privacy', title: tx('securityCenter.fact.privacy.title', 'Trust continuity'), body: tx('securityCenter.fact.privacy.body', 'Security remains connected to privacy rights, legal notice, and data control flows.'), icon: 'shield-checkmark-outline' },
        ]}
        changeLogTitle={tx('securityCenter.changelog.title', 'What changed in this security experience')}
        changeLogItems={[
          tx('securityCenter.changelog.1', 'Reframed security posture into a premium public trust-center surface.'),
          tx('securityCenter.changelog.2', 'Connected security, privacy, and GDPR pages into one legal-trust family.'),
          tx('securityCenter.changelog.3', 'Made public security language more operational and less generic.'),
        ]}
        trustPanelTitle={tx('securityCenter.trustPanel.title', 'What this means for you')}
        trustPanelItems={[
          tx('securityCenter.trustPanel.item1', 'You can assess trust posture before you create an account or upgrade.'),
          tx('securityCenter.trustPanel.item2', 'Security is linked to real platform operations, not just marketing claims.'),
          tx('securityCenter.trustPanel.item3', 'Privacy and legal trust pages stay connected when evaluating sensitive workflows.'),
        ]}
        sidebarTitle={tx('securityCenter.sidebar.title', 'Navigate security topics')}
        sidebarSearchPlaceholder={tx('securityCenter.sidebar.search', 'Search security topics')}
        sidebarCtaTitle={tx('securityCenter.sidebar.ctaTitle', 'Need a trust follow-up?')}
        sidebarCtaBody={tx('securityCenter.sidebar.ctaBody', 'Move into Privacy, GDPR, or Help depending on whether your question is legal, operational, or rights-based.')}
        sidebarCtaLabel={tx('securityCenter.sidebar.ctaButton', 'Open Help & Support')}
        sidebarCtaHref="/help"
        sections={sections}
        pinSectionLabel={tx('securityCenter.section.focus', 'Pin section')}
        actionHubTitle={tx('securityCenter.actionHub.title', 'Continue the trust review with the right surface')}
        actionHubSubtitle={tx('securityCenter.actionHub.subtitle', 'Users often need the next linked trust page right after security — privacy, GDPR, or support — so those actions stay visible here.')}
        actionHubOpenLabel={tx('securityCenter.actionHub.open', 'Open flow')}
        actionCards={[
          { id: 'privacy', title: tx('securityCenter.actions.privacy.title', 'Review Privacy Policy'), body: tx('securityCenter.actions.privacy.body', 'See what data is collected, used, shared, and retained.'), icon: 'shield-checkmark-outline', href: '/privacy-policy' },
          { id: 'gdpr', title: tx('securityCenter.actions.gdpr.title', 'Review GDPR rights'), body: tx('securityCenter.actions.gdpr.body', 'Understand rights, lawful basis, and transfer safeguards.'), icon: 'globe-outline', href: '/gdpr' },
          { id: 'support', title: tx('securityCenter.actions.support.title', 'Contact support'), body: tx('securityCenter.actions.support.body', 'Escalate trust, access, or security questions through Help & Support.'), icon: 'mail-open-outline', href: '/help' },
        ]}
        contactTitle={tx('securityCenter.contact.title', 'Security, trust, or platform-risk questions')}
        contactBody={tx('securityCenter.contact.body', 'If you need help evaluating product security, trust posture, or incident-readiness claims, contact our support workflow and we will route the request appropriately.')}
        contactItems={[
          { id: 'support', label: tx('securityCenter.contact.support', 'Help & Support workspace'), icon: 'help-buoy-outline' },
          { id: 'privacy', label: tx('securityCenter.contact.privacy', 'Privacy and GDPR pages remain linked for rights-based follow-up'), icon: 'shield-checkmark-outline' },
          { id: 'status', label: tx('securityCenter.contact.status', 'Operational trust also depends on monitoring and recovery continuity'), icon: 'pulse-outline' },
        ]}
      />
    </PublicPageShell>
  );
}

export default function SecuritySettingsScreen() {
  const { user } = useAuth();
  /* Unauthenticated visitors see the public Security Information page */
  if (!user) return <SecurityInfoPage />;
  /* Delegates to the authenticated settings inner component so its hooks
   * are always called in a stable order (rules-of-hooks compliant). */
  return <SecuritySettingsAuthenticated />;
}

function SecuritySettingsAuthenticated() {
  const router = useRouter();
  const params = useLocalSearchParams<{ prompt_passkey?: string; next?: string }>();
  const { colors, _darkMode } = useTheme();
  const { t } = useTranslation();

  /* Authenticated users see the security settings panel */
  const C = { bg: colors.bg, card: colors.card, cardBorder: colors.border, text: colors.text, textSec: colors.textSec, textMuted: colors.textMuted, ...statusColors };
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<any>(null);
  const [geoInfo, setGeoInfo] = useState<any>(null);

  // PIN state
  const [showPinSetup, setShowPinSetup] = useState(false);
  const [newPin, setNewPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [pinLoading, setPinLoading] = useState(false);

  // Passkey state
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [passkeyCredentials, setPasskeyCredentials] = useState<any[]>([]);
  const [passkeyCredentialBusy, setPasskeyCredentialBusy] = useState(false);
  const passkeyPromptHandled = useRef(false);

  // OTP preference
  const [_otpPref, setOtpPref] = useState('email');
  const [_otpPrefLoading, setOtpPrefLoading] = useState(false);

  // Backup codes
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [backupLoading, setBackupLoading] = useState(false);

  // Login history
  const [loginHistory, setLoginHistory] = useState<any[]>([]);

  const loadStatus = useCallback(async () => {
    try {
      setLoading(true);
      const [statusRes, geoRes, passkeyRes] = await Promise.all([
        api.get('/auth/2fa/status'),
        api.get('/geo/detect').catch(() => ({ data: null })),
        api.get('/auth/biometric/webauthn/credentials').catch(() => ({ data: { credentials: [] } })),
      ]);
      setStatus(statusRes.data);
      setGeoInfo(geoRes?.data || null);
      setPasskeyCredentials(Array.isArray(passkeyRes?.data?.credentials) ? passkeyRes.data.credentials : []);
    } catch (e) {
      console.error('Failed to load security status', e);
      handleAppRecoverableError({
        scope: 'security.load-status',
        error: e,
        message: 'Unable to load security status right now.',
        onRetry: () => { void loadStatus(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const res = await api.get('/auth/security/login-history');
      setLoginHistory(res.data?.events || []);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'security.load-history',
        error,
        message: 'Unable to load login history right now.',
        onRetry: () => { void loadHistory(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadHistory();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { loadStatus(); } catch (error) { handleAppRecoverableError({ scope: 'security.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const handleToggle2FA = async () => {
    try {
      if (status?.two_fa_enabled) {
        await api.post('/auth/2fa/disable');
      } else {
        const res = await api.post('/auth/2fa/enable');
        if (res.data?.backup_codes) {
          setBackupCodes(res.data.backup_codes);
        }
      }
      await loadStatus();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to update 2FA');
    }
  };

  const handleSetPin = async () => {
    if (newPin.length !== 4 || !newPin.match(/^\d{4}$/)) {
      Alert.alert('Invalid PIN', 'PIN must be exactly 4 digits');
      return;
    }
    if (newPin !== confirmPin) {
      Alert.alert('Mismatch', 'PINs do not match');
      return;
    }
    setPinLoading(true);
    try {
      await api.post('/auth/biometric/set-pin', { user_id: user?.user_id, pin: newPin });
      Alert.alert('Success', 'PIN set successfully');
      setShowPinSetup(false);
      setNewPin('');
      setConfirmPin('');
      await loadStatus();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to set PIN');
    } finally {
      setPinLoading(false);
    }
  };

  const handleRegisterPasskey = async () => {
    if (false) {
      console.error("Passkey not supported on web!");
      Alert.alert('Unavailable', 'Passkey registration requires a web browser with biometric support.');
      return;
    }
    setPasskeyLoading(true);
    try {
      const optRes = await api.post('/auth/biometric/webauthn-register-options', { user_id: user?.user_id });
      const opts = normalizeRegistrationOptions(optRes.data);
      console.log("WebAuthn opts:", opts);

      const credential = await (navigator as any).credentials.create({
        publicKey: opts,
      }) as any;
      console.log("WebAuthn credential:", credential);

      if (!credential) {
         console.error("No credential returned!");
         return;
      }

      await api.post('/auth/biometric/webauthn-register-complete', {
        user_id: user?.user_id,
        challenge_id: optRes.data?.challenge_id,
        credential: serializeWebAuthnCredential(credential),
      });
      Alert.alert('Success', 'Passkey registered successfully! You can now use biometric login.');
      await loadStatus();
    } catch (e: any) {
      console.error("Passkey catch block error:", e);
      if (e?.name !== 'NotAllowedError') {
        Alert.alert('Error', e?.response?.data?.detail || 'Passkey registration failed');
      }
    } finally {
      setPasskeyLoading(false);
    }
  };

  const handleRemovePasskey = async (credentialId: string) => {
    if (!credentialId || passkeyCredentialBusy) return;
    setPasskeyCredentialBusy(true);
    try {
      await api.delete(`/auth/biometric/webauthn/credentials/${encodeURIComponent(credentialId)}`);
      await loadStatus();
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to remove passkey credential');
    } finally {
      setPasskeyCredentialBusy(false);
    }
  };

  useEffect(() => {
    if (passkeyPromptHandled.current) return;
    if (String(params.prompt_passkey || '') !== '1') return;
    passkeyPromptHandled.current = true;
    Alert.alert(
      'Enable biometric login',
      'Register fingerprint/Face ID passkey for quicker and safer sign-in?',
      [
        {
          text: 'Not now',
          style: 'cancel',
          onPress: () => {
            if (params.next && typeof params.next === 'string') {
              router.replace(params.next as any);
            }
          },
        },
        {
          text: 'Enable',
          onPress: () => { void handleRegisterPasskey(); },
        },
      ]
    );
  }, [handleRegisterPasskey, params.next, params.prompt_passkey, router]);

  const handleOtpPrefChange = async (pref: string) => {
    setOtpPrefLoading(true);
    try {
      await api.post('/auth/otp-preference', { preference: pref });
      setOtpPref(pref);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to update preference');
    } finally {
      setOtpPrefLoading(false);
    }
  };

  const handleRegenBackupCodes = async () => {
    setBackupLoading(true);
    try {
      const res = await api.post('/auth/2fa/backup-codes/regenerate');
      setBackupCodes(res.data?.backup_codes || []);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Failed to regenerate codes');
    } finally {
      setBackupLoading(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <SecuritySettingsSkeleton />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <FadeSlideIn>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ padding: 20, paddingBottom: 60, maxWidth: 600, width: '100%', alignSelf: 'center' }}>
          {/* Header */}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 24 }}>
            <TouchableOpacity onPress={() => router.back()} data-testid="security-back-btn" testID="security-back-btn" style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: C.card, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="arrow-back" size={20} color={C.text} />
            </TouchableOpacity>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 22, fontWeight: '700', color: C.text }} data-testid="security-title" testID="security-title">{t('securitySettings.title')}</Text>
              <Text style={{ fontSize: 13, color: C.textMuted }}>{t("autofix.watchSweep1.manage.your.account.security")}</Text>
            </View>
          </View>

          {/* 2FA Section */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-2fa-section" testID="security-2fa-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.green, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="shield-checkmark" size={20} color={C.green} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{t("privacySecurity.twoFactor.title")}</Text>
                <Text style={{ fontSize: 12, color: C.textMuted }}>
                  {status?.is_exempt ? 'Managed by organization' : status?.two_fa_enabled ? 'Enabled' : 'Not enabled'}
                </Text>
              </View>
              {!status?.is_exempt && (
                <Switch
                  value={status?.two_fa_enabled}
                  onValueChange={handleToggle2FA}
                  trackColor={{ false: C.cardBorder, true: C.green + '60' }}
                  thumbColor={status?.two_fa_enabled ? C.green : C.textMuted}
                  data-testid="security-2fa-toggle" testID="security-2fa-toggle"
                />
              )}
            </View>
            {status?.two_fa_enabled && (
              <Text style={{ fontSize: 12, color: C.textSec }}>{t("autofix.watchSweep1.backup.codes.remaining")}{status?.backup_codes_remaining || 0}
              </Text>
            )}
          </View>

          {/* Backup Codes */}
          {status?.two_fa_enabled && (
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-backup-section" testID="security-backup-section">
              <Text style={{ fontSize: 16, fontWeight: '600', color: C.text, marginBottom: 12 }}>{t("securityDashboard.score.backupCodes")}</Text>
              {backupCodes ? (
                <View style={{ backgroundColor: C.bg, borderRadius: 12, padding: 16, marginBottom: 12 }}>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                    {backupCodes.map((code, i) => (
                      <View key={i} style={{ backgroundColor: C.cardBorder, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 }}>
                        <Text style={{ fontSize: 13, fontWeight: '600', color: C.green, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }} data-testid={`backup-code-${i}`} testID={`backup-code-${i}`}>{code}</Text>
                      </View>
                    ))}
                  </View>
                  <Text style={{ fontSize: 11, color: C.yellow, marginTop: 10 }}>{t("autofix.watchSweep1.save.these.codes.securely.each.can.only.be")}</Text>
                </View>
              ) : null}
              <TouchableOpacity
                onPress={handleRegenBackupCodes}
                disabled={backupLoading}
                style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }}
                data-testid="security-regen-backup-btn" testID="security-regen-backup-btn"
              >
                {backupLoading ? <ActivityIndicator color={C.blue} /> : (
                  <Text style={{ color: C.blue, fontWeight: '600', fontSize: 14 }}>
                    {backupCodes ? 'Regenerate Codes' : 'View Backup Codes'}
                  </Text>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* PIN Setup */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-pin-section" testID="security-pin-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(C.blue, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="keypad" size={20} color={C.blue} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{t("autofix.watchSweep1.pin.login")}</Text>
                <Text style={{ fontSize: 12, color: C.textMuted }}>
                  {status?.has_pin ? 'PIN is set up' : 'Set a 4-digit PIN for quick login'}
                </Text>
              </View>
              <View style={{ backgroundColor: status?.has_pin ? (globalThis as any).__alphaColor(C.green, '20') : C.yellow + '20', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 }}>
                <Text style={{ fontSize: 11, fontWeight: '600', color: status?.has_pin ? C.green : C.yellow }}>
                  {status?.has_pin ? 'Active' : 'Not set'}
                </Text>
              </View>
            </View>

            {showPinSetup ? (
              <View style={{ gap: 10 }}>
                <TextInput
                  placeholder="New 4-digit PIN"
                  placeholderTextColor={C.textMuted}
                  value={newPin}
                  onChangeText={setNewPin}
                  keyboardType="number-pad"
                  maxLength={4}
                  secureTextEntry
                  style={{ backgroundColor: C.bg, borderRadius: 12, padding: 14, color: C.text, fontSize: 16, borderWidth: 1, borderColor: C.cardBorder }}
                  data-testid="security-pin-new" testID="security-pin-new"
                />
                <TextInput
                  placeholder="Confirm PIN"
                  placeholderTextColor={C.textMuted}
                  value={confirmPin}
                  onChangeText={setConfirmPin}
                  keyboardType="number-pad"
                  maxLength={4}
                  secureTextEntry
                  style={{ backgroundColor: C.bg, borderRadius: 12, padding: 14, color: C.text, fontSize: 16, borderWidth: 1, borderColor: C.cardBorder }}
                  data-testid="security-pin-confirm" testID="security-pin-confirm"
                />
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <TouchableOpacity onPress={() => { setShowPinSetup(false); setNewPin(''); setConfirmPin(''); }} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: C.cardBorder, alignItems: 'center' }} data-testid="security-pin-cancel-btn" testID="security-pin-cancel-btn">
                    <Text style={{ color: C.text, fontWeight: '600' }}>{t("admin.onboardingAB.actions.cancel")}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={handleSetPin} disabled={pinLoading} style={{ flex: 1, padding: 14, borderRadius: 12, backgroundColor: C.blue, alignItems: 'center' }} data-testid="security-pin-save-btn" testID="security-pin-save-btn">
                    {pinLoading ? <ActivityIndicator color="#FFF" /> : <Text style={{ color: colors.primaryText, fontWeight: '600' }}>{t("autofix.watchSweep1.save.pin")}</Text>}
                  </TouchableOpacity>
                </View>
              </View>
            ) : (
              <TouchableOpacity onPress={() => setShowPinSetup(true)} style={{ backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }} data-testid="security-pin-setup-btn" testID="security-pin-setup-btn">
                <Text style={{ color: C.blue, fontWeight: '600', fontSize: 14 }}>{status?.has_pin ? 'Change PIN' : 'Set Up PIN'}</Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Passkey / Biometric */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-passkey-section" testID="security-passkey-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.purple, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="finger-print" size={20} color={colors.purpleText} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{t("autofix.watchSweep1.passkey.biometric")}</Text>
                <Text style={{ fontSize: 12, color: C.textMuted }} data-testid="security-passkey-status-subtitle" testID="security-passkey-status-subtitle">
                  {status?.has_passkey
                    ? 'Passkey registered'
                    : status?.passkey_rollout_enabled
                      ? 'Use FaceID, fingerprint, or device PIN'
                      : 'Passkey rollout pending for this account'}
                </Text>
              </View>
              <View style={{ backgroundColor: status?.has_passkey ? (C.green + '20') : (C.yellow + '20'), borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 }} data-testid="security-passkey-status-badge" testID="security-passkey-status-badge">
                <Text style={{ fontSize: 11, fontWeight: '600', color: status?.has_passkey ? C.green : C.yellow }} data-testid="security-passkey-status-badge-text" testID="security-passkey-status-badge-text">
                  {status?.has_passkey ? 'Active' : 'Not set'}
                </Text>
              </View>
            </View>
            <TouchableOpacity
              onPress={handleRegisterPasskey}
              style={{ backgroundColor: (globalThis as any).__alphaColor(colors.purple, '15'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.purple, '30') }}
              data-testid="security-passkey-register-btn" testID="security-passkey-register-btn"
            >
              {passkeyLoading ? <ActivityIndicator color={colors.purpleText} /> : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="finger-print" size={16} color={colors.purpleText} />
                  <Text style={{ color: colors.purpleText, fontWeight: '600', fontSize: 14 }}>
                    {status?.has_passkey ? 'Re-register Passkey' : 'Register Passkey'}
                  </Text>
                </View>
              )}
            </TouchableOpacity>

            {passkeyCredentials.length > 0 && (
              <View style={{ marginTop: 14, gap: 8 }} data-testid="security-passkey-credential-list" testID="security-passkey-credential-list">
                {passkeyCredentials.map((item, idx) => (
                  <View
                    key={`${item.credential_id}-${idx}`}
                    style={{
                      borderRadius: 10,
                      borderWidth: 1,
                      borderColor: C.cardBorder,
                      backgroundColor: C.bg,
                      padding: 10,
                      flexDirection: 'row',
                      alignItems: 'center',
                      gap: 10,
                    }}
                    data-testid={`security-passkey-credential-${idx}`}
                    testID={`security-passkey-credential-${idx}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }} data-testid={`security-passkey-credential-name-${idx}`} testID={`security-passkey-credential-name-${idx}`}>
                        {item.nickname || 'This device'}
                      </Text>
                      <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid={`security-passkey-credential-last-used-${idx}`} testID={`security-passkey-credential-last-used-${idx}`}>
                        Last used: {item.last_used_at ? new Date(item.last_used_at).toLocaleString() : 'Never'}
                      </Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => { void handleRemovePasskey(item.credential_id); }}
                      disabled={passkeyCredentialBusy}
                      style={{
                        borderRadius: 8,
                        borderWidth: 1,
                        borderColor: (globalThis as any).__alphaColor(C.red, '35'),
                        backgroundColor: (globalThis as any).__alphaColor(C.red, '12'),
                        paddingHorizontal: 10,
                        paddingVertical: 7,
                      }}
                      data-testid={`security-passkey-remove-btn-${idx}`}
                      testID={`security-passkey-remove-btn-${idx}`}
                    >
                      <Text style={{ color: C.red, fontSize: 12, fontWeight: '700' }}>Remove</Text>
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            )}
          </View>

          {/* Geo Info */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-geo-section" testID="security-geo-section">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="globe" size={20} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 16, fontWeight: '600', color: C.text }}>{t("autofix.watchSweep1.detected.location")}</Text>
                <Text style={{ fontSize: 12, color: C.textMuted }}>
                  {geoInfo?.country_name || geoInfo?.detected_country || 'Unknown'}{t("autofix.watchSweep1.otp.via")}{geoInfo?.otp_methods?.join(' or ') || 'email'}
                </Text>
              </View>
            </View>
          </View>

          {/* Login History */}
          <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: C.cardBorder }} data-testid="security-history-section" testID="security-history-section">
            <Text style={{ fontSize: 16, fontWeight: '600', color: C.text, marginBottom: 16 }}>{t("autofix.watchSweep1.recent.login.activity")}</Text>
            {loginHistory.length === 0 ? (
              <Text style={{ fontSize: 13, color: C.textMuted, textAlign: 'center', paddingVertical: 20 }}>{t("autofix.watchSweep1.no.recent.activity")}</Text>
            ) : (
              loginHistory.slice(0, 10).map((event, i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderTopWidth: i > 0 ? 1 : 0, borderTopColor: C.cardBorder }}>
                  <Ionicons
                    name={event.event_type === 'login_success' ? 'checkmark-circle' : event.event_type === 'logout' ? 'log-out' : 'close-circle'}
                    size={18}
                    color={event.event_type === 'login_success' ? C.green : event.event_type === 'logout' ? C.yellow : C.red}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 13, color: C.text, fontWeight: '500' }}>
                      {event.event_type?.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                    </Text>
                    <Text style={{ fontSize: 11, color: C.textMuted }}>
                      {event.timestamp ? new Date(event.timestamp).toLocaleString() : ''}
                    </Text>
                  </View>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>{event.severity || ''}</Text>
                </View>
              ))
            )}
          </View>

          {/* Account Lock Status */}
          {status?.account_locked && (
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), borderRadius: 16, padding: 20, marginBottom: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30') }} data-testid="security-locked-warning" testID="security-locked-warning">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Ionicons name="warning" size={24} color={C.red} />
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 16, fontWeight: '600', color: C.red }}>{t("autofix.watchSweep1.account.locked")}</Text>
                  <Text style={{ fontSize: 13, color: C.textSec }}>{t("autofix.watchSweep1.too.many.failed.otp.attempts.contact.support.to")}</Text>
                </View>
              </View>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
      </FadeSlideIn>
    </AppShell>
  );
}
