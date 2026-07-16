/**
 * /invite-accept
 * ──────────────
 * Public landing page for platform-employee invitation acceptance.
 * Reads ?token= from URL, verifies it, renders a compact form, then calls
 * POST /api/admin/employees/invitations/accept. On success stores session_token
 * and routes the new user to a role-tailored non-admin-safe landing route
 * (e.g., Support Team → /my-tickets). See `getLandingRouteForRole()`.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { getLandingRouteForRole } from '../src/lib/platformRoleLanding';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

const API = resolveRuntimeBaseUrl();

interface Invitation {
  valid: boolean;
  email?: string;
  platform_role?: string;
  premium_access?: boolean;
  invited_by_email?: string;
  expires_at?: string;
  reason?: string;
  status?: string;
}

function getTokenFromUrl(): string {
  if (Platform.OS !== 'web') return '';
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get('token') || '';
  } catch {
    return '';
  }
}

function expiresInLabel(iso?: string): string {
  if (!iso) return '';
  try {
    const diff = new Date(iso).getTime() - Date.now();
    if (diff <= 0) return 'expired';
    const h = Math.floor(diff / 3600000);
    if (h >= 24) return `in ${Math.floor(h / 24)}d ${h % 24}h`;
    if (h >= 1) return `in ${h}h`;
    return `in ${Math.max(1, Math.floor(diff / 60000))}m`;
  } catch {
    return '';
  }
}

export default function InviteAcceptPage() {
  const { t } = useTranslation();
  t('i18n.route.invite-accept.probe');
  const { colors } = useTheme();
  const { refreshUser } = useAuth();
  const { width } = useWindowDimensions();
  const compact = width < 640;
  const params = useLocalSearchParams<{ token?: string }>();

  const token = useMemo(() => {
    const fromRouter = typeof params.token === 'string' ? params.token : '';
    return fromRouter || getTokenFromUrl();
  }, [params.token]);

  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [loadingInv, setLoadingInv] = useState(true);
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [confirmingDecline, setConfirmingDecline] = useState(false);

  const doDecline = useCallback(async () => {
    if (!token) return;
    setError(null);
    setConfirmingDecline(false);
    setDeclining(true);
    try {
      const res = await fetch(`${API}/api/admin/employees/invitations/decline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(msg || `HTTP ${res.status}`);
      }
      setDeclined(true);
    } catch (e: any) {
      setError(String(e?.message || 'Could not decline right now'));
    } finally {
      setDeclining(false);
    }
  }, [token]);

  const decline = useCallback(() => {
    if (!token) return;
    setError(null);
    setConfirmingDecline(true);
  }, [token]);

  useEffect(() => {
    if (!token) {
      setInvitation({ valid: false, reason: 'invalid_token' });
      setLoadingInv(false);
      return;
    }
    (async () => {
      try {
        const res = await fetch(`${API}/api/admin/employees/invitations/verify?token=${encodeURIComponent(token)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setInvitation(data);
      } catch (e: any) {
        setInvitation({ valid: false, reason: e?.message || 'verify_failed' });
      } finally {
        setLoadingInv(false);
      }
    })();
  }, [token]);

  const accept = useCallback(async () => {
    setError(null);
    if (!password || password.length < 8) {
      setError(t('validation.password_min_length'));
      return;
    }
    if (password !== confirm) {
      setError(t('validation.passwords_do_not_match'));
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/admin/employees/invitations/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password, name: name || invitation?.email?.split('@')[0] }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || 'Accept failed');
      }
      if (data?.session_token && typeof localStorage !== 'undefined') {
        try {
          localStorage.setItem('session_token', data.session_token);
          localStorage.setItem('user_id', data.user_id);
          localStorage.setItem('email', data.email);
        } catch (error) { handleAppRecoverableError({ scope: 'invite-accept.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
      setAccepted(true);
      // Re-fetch auth state so RouteAccessGuard doesn't kick us to /auth/login
      // on the role-aware redirect below — it blocks when `user` is still null.
      try { await refreshUser?.(); } catch (error) { handleAppRecoverableError({ scope: 'invite-accept.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      const landingRoute = getLandingRouteForRole(data?.platform_role || invitation?.platform_role);
      setTimeout(() => {
        try {
          router.replace(landingRoute as any);
        } catch (error) {
          handleAppRecoverableError({
            scope: 'invite-accept.navigate-landing',
            error,
            message: 'Could not navigate to your landing page.',
            setError,
            onRetry: () => { router.replace(landingRoute as any); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
        }
      }, 1200);
    } catch (e: any) {
      setError(String(e?.message || 'Something went wrong'));
    } finally {
      setSubmitting(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, password, confirm, name, invitation?.email, t]);

  if (loadingInv) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="invite-accept-loading" testID="invite-accept-loading">
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={{ color: colors.textSec, marginTop: 10, fontSize: 13 }}>Verifying invitation…</Text>
      </View>
    );
  }

  if (!invitation?.valid) {
    const reasonLabel: Record<string, string> = {
      invalid_token: 'This invitation link is invalid.',
      expired: 'This invitation has expired. Please ask the admin to send a new one.',
      already_used: 'This invitation has already been used. Please sign in normally.',
      verify_failed: 'We couldn\'t verify your invitation right now. Please try again.',
    };
    const reasonKey = invitation?.reason || 'invalid_token';
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="invite-accept-invalid" testID="invite-accept-invalid">
        <View style={{ maxWidth: 420, width: '100%', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 24, alignItems: 'center', gap: 10 }}>
          <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="alert-circle" size={22} color={colors.error} />
          </View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.3, textAlign: 'center' }}>{t("autofix.batch2.invitation.unavailable")}</Text>
          <Text style={{ color: colors.textSec, fontSize: 13, textAlign: 'center', lineHeight: 20 }}>
            {reasonLabel[reasonKey] || reasonLabel.invalid_token}
          </Text>
          <TouchableOpacity
            onPress={() => { try { router.replace('/auth/login'); } catch (error) { handleAppRecoverableError({ scope: 'invite-accept.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }}
            data-testid="invite-accept-back-to-login" testID="invite-accept-back-to-login"
            style={{ marginTop: 10, borderRadius: 8, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 9 }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{t("autofix.batch2.back.to.sign.in")}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (declined) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="invite-accept-declined" testID="invite-accept-declined">
        <View style={{ maxWidth: 420, width: '100%', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 24, alignItems: 'center', gap: 10 }}>
          <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: (globalThis as any).__alphaColor(colors.textMuted, '22'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="close-circle" size={24} color={colors.textSec} />
          </View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>Invitation declined</Text>
          <Text style={{ color: colors.textSec, fontSize: 13, textAlign: 'center', lineHeight: 20 }}>
            Thanks for letting us know. Your account has not been changed. If this was a mistake, ask the admin to send a new invite.
          </Text>
          <TouchableOpacity
            onPress={() => { try { router.replace('/auth/login'); } catch (error) { handleAppRecoverableError({ scope: 'invite-accept.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }}
            data-testid="invite-declined-back-to-login" testID="invite-declined-back-to-login"
            style={{ marginTop: 10, borderRadius: 8, backgroundColor: colors.primary, paddingHorizontal: 16, paddingVertical: 9 }}
          >
            <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{t("autofix.batch2.back.to.sign.in")}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  if (accepted) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="invite-accept-success" testID="invite-accept-success">
        <View style={{ maxWidth: 420, width: '100%', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 24, alignItems: 'center', gap: 10 }}>
          <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.successSoft, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="checkmark-circle" size={24} color={colors.successText} />
          </View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }}>Welcome aboard</Text>
          <Text style={{ color: colors.textSec, fontSize: 13, textAlign: 'center' }}>Your account is ready. Redirecting you to the platform…</Text>
          <ActivityIndicator size="small" color={colors.primary} />
        </View>
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: compact ? 16 : 24 }}>
      <View style={{ maxWidth: 460, width: '100%', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: compact ? 20 : 28 }} data-testid="invite-accept-form" testID="invite-accept-form">
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: colors.success }} />
          <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.2 }}>
            Platform Invitation
          </Text>
        </View>
        <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5, marginTop: 10 }} data-testid="invite-accept-title" testID="invite-accept-title">
          Accept your invitation
        </Text>
        <Text style={{ color: colors.textSec, fontSize: 13, marginTop: 4, lineHeight: 20 }}>
          <Text style={{ color: colors.text, fontWeight: '700' }}>{invitation.invited_by_email}</Text> invited you to join as a{' '}
          <Text style={{ color: colors.text, fontWeight: '700' }}>{invitation.platform_role}</Text>.
        </Text>

        <View style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 12, gap: 6 }} data-testid="invite-accept-meta" testID="invite-accept-meta">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>Email</Text>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }} data-testid="invite-accept-email" testID="invite-accept-email">{invitation.email}</Text>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>Role</Text>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }} data-testid="invite-accept-role" testID="invite-accept-role">{invitation.platform_role}</Text>
          </View>
          {invitation.premium_access ? (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>Access</Text>
              <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>Premium</Text>
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 }}>Expires</Text>
            <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '600' }} data-testid="invite-accept-expires" testID="invite-accept-expires">{expiresInLabel(invitation.expires_at)}</Text>
          </View>
        </View>

        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginTop: 18, marginBottom: 6 }}>Your name (optional)</Text>
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="Jane Doe"
          placeholderTextColor={colors.textMuted}
          data-testid="invite-accept-name-input" testID="invite-accept-name-input"
          style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, padding: 11, fontSize: 13, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
        />

        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginTop: 12, marginBottom: 6 }}>Create password</Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="min 8 characters"
          placeholderTextColor={colors.textMuted}
          data-testid="invite-accept-password-input" testID="invite-accept-password-input"
          style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, padding: 11, fontSize: 13, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
        />

        <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, marginTop: 12, marginBottom: 6 }}>Confirm password</Text>
        <TextInput
          value={confirm}
          onChangeText={setConfirm}
          secureTextEntry
          placeholder="repeat password"
          placeholderTextColor={colors.textMuted}
          data-testid="invite-accept-confirm-input" testID="invite-accept-confirm-input"
          style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, padding: 11, fontSize: 13, ...(Platform.OS === 'web' ? { outlineStyle: 'none' } as any : {}) }}
        />

        {error ? (
          <View style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '40'), backgroundColor: colors.errorSoft, padding: 10, flexDirection: 'row', gap: 8, alignItems: 'center' }} data-testid="invite-accept-error" testID="invite-accept-error">
            <Ionicons name="alert-circle" size={15} color={colors.error} />
            <Text style={{ color: colors.error, fontSize: 12, fontWeight: '600', flex: 1 }}>{error}</Text>
          </View>
        ) : null}

        <TouchableOpacity
          onPress={accept}
          disabled={submitting || declining}
          data-testid="invite-accept-submit-button" testID="invite-accept-submit-button"
          style={{
            marginTop: 18,
            borderRadius: 10,
            backgroundColor: colors.primary,
            paddingVertical: 12,
            alignItems: 'center',
            flexDirection: 'row',
            justifyContent: 'center',
            gap: 8,
            opacity: (submitting || declining) ? 0.6 : 1,
          }}
        >
          {submitting ? <ActivityIndicator size="small" color={colors.primaryText} /> : null}
          <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 13 }}>
            {submitting ? 'Creating your account…' : 'Accept & join'}
          </Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={decline}
          disabled={submitting || declining}
          data-testid="invite-decline-button" testID="invite-decline-button"
          style={{
            marginTop: 10,
            borderRadius: 10,
            backgroundColor: 'transparent',
            borderWidth: 1,
            borderColor: colors.border,
            paddingVertical: 11,
            alignItems: 'center',
            flexDirection: 'row',
            justifyContent: 'center',
            gap: 8,
            opacity: (submitting || declining) ? 0.6 : 1,
          }}
        >
          {declining ? <ActivityIndicator size="small" color={colors.textSec} /> : null}
          <Text style={{ color: colors.textSec, fontWeight: '700', fontSize: 12 }}>
            {declining ? 'Declining…' : 'Decline invitation'}
          </Text>
        </TouchableOpacity>

        {confirmingDecline ? (
          <View
            style={{
              position: Platform.OS === 'web' ? ('fixed' as any) : 'absolute',
              top: 0, left: 0, right: 0, bottom: 0,
              backgroundColor: 'rgba(2,6,23,0.55)',
              alignItems: 'center', justifyContent: 'center',
              padding: 20,
              zIndex: 1000,
            }}
            data-testid="invite-decline-confirm-modal" testID="invite-decline-confirm-modal"
          >
            <View style={{ maxWidth: 400, width: '100%', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 22 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                <View style={{ width: 34, height: 34, borderRadius: 17, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="alert-circle" size={18} color={colors.error} />
                </View>
                <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>Decline invitation?</Text>
              </View>
              <Text style={{ color: colors.textSec, fontSize: 13, lineHeight: 20, marginBottom: 16 }}>
                This cannot be undone — the admin will need to send you a new invite if you change your mind.
              </Text>
              <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'flex-end' }}>
                <TouchableOpacity
                  onPress={() => setConfirmingDecline(false)}
                  data-testid="invite-decline-cancel" testID="invite-decline-cancel"
                  style={{ paddingHorizontal: 14, paddingVertical: 9, borderRadius: 8, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }}
                >
                  <Text style={{ color: colors.textSec, fontSize: 12, fontWeight: '700' }}>Keep invitation</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={doDecline}
                  data-testid="invite-decline-confirm" testID="invite-decline-confirm"
                  style={{ paddingHorizontal: 14, paddingVertical: 9, borderRadius: 8, backgroundColor: colors.error }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>Yes, decline</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        ) : null}
      </View>
    </View>
  );
}