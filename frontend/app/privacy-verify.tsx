/**
 * /privacy-verify?token=…
 * ───────────────────────
 * Public landing page the user reaches by clicking their email link.
 * Verifies token → shows record counts → user confirms → executes action.
 * For export, streams a JSON file download. For delete, shows success summary.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Platform, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { resolveRuntimeBaseUrl } from '../src/utils/runtimeBaseUrl';

const API = resolveRuntimeBaseUrl();

interface VerifyResp {
  request_id: string;
  action: 'export' | 'delete';
  record_counts: Record<string, number>;
  expires_at_utc?: string;
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

export default function PrivacyVerify() {
  const { t } = useTranslation();
  t('i18n.route.privacy-verify.probe');
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const isMobile = width < 720;

  const token = useMemo(getTokenFromUrl, []);
  const [verifying, setVerifying] = useState(true);
  const [verifyErr, setVerifyErr] = useState<string | null>(null);
  const [info, setInfo] = useState<VerifyResp | null>(null);

  const [executing, setExecuting] = useState(false);
  const [execErr, setExecErr] = useState<string | null>(null);
  const [done, setDone] = useState<{ kind: 'export' | 'delete'; summary: any } | null>(null);

  const verify = useCallback(async () => {
    if (!token) {
      setVerifying(false);
      setVerifyErr('Missing token. Please use the link we emailed you.');
      return;
    }
    try {
      const res = await fetch(`${API}/api/gdpr/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ token }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || 'Invalid or expired link');
      }
      const data: VerifyResp = await res.json();
      setInfo(data);
    } catch (e: any) {
      setVerifyErr(e.message || 'Link verification failed.');
    } finally {
      setVerifying(false);
    }
  }, [token]);

  useEffect(() => {
    verify();
  }, [verify]);

  const execute = useCallback(async () => {
    if (!token) return;
    setExecuting(true);
    setExecErr(null);
    try {
      const res = await fetch(`${API}/api/gdpr/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify({ token, confirm: true }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || 'Execution failed');
      }
      const payload = await res.json();
      if (info?.action === 'export' && Platform.OS === 'web') {
        // Trigger file download of the JSON payload
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `realaicoach_data_${payload.request_id}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      }
      setDone({ kind: info!.action, summary: payload });
    } catch (e: any) {
      setExecErr(e.message || 'Something went wrong.');
    } finally {
      setExecuting(false);
    }
  }, [token, info]);

  const card = {
    backgroundColor: colors.card,
    borderColor: colors.glassBorder,
    borderWidth: 1,
    borderRadius: 16,
    padding: isMobile ? 20 : 32,
    maxWidth: 560,
    width: '100%' as const,
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 20 }} data-testid="privacy-verify-page">
      <View style={card}>
        {verifying ? (
          <View style={{ alignItems: 'center', paddingVertical: 40 }} data-testid="privacy-verify-loading">
            <ActivityIndicator color={colors.text} />
            <Text style={{ color: colors.textSec, marginTop: 12 }}>Verifying your link…</Text>
          </View>
        ) : verifyErr ? (
          <View data-testid="privacy-verify-error">
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
              <Ionicons name="close-circle-outline" size={24} color="#EF4444" />
              <Text style={{ color: colors.text, marginLeft: 8, fontSize: 18, fontWeight: '700' }}>Link issue</Text>
            </View>
            <Text style={{ color: colors.textSec, marginBottom: 20 }}>{verifyErr}</Text>
            <TouchableOpacity
              data-testid="privacy-verify-retry"
              onPress={() => router.replace('/privacy-request')}
              style={{ backgroundColor: colors.primary, padding: 12, borderRadius: 10, alignItems: 'center' }}>
              <Text style={{ color: colors.primaryText, fontWeight: '700' }}>Request a new link</Text>
            </TouchableOpacity>
          </View>
        ) : done ? (
          <View data-testid="privacy-verify-done">
            <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
              <Ionicons name="checkmark-circle-outline" size={26} color="#10B981" />
              <Text style={{ color: colors.text, marginLeft: 8, fontSize: 20, fontWeight: '800' }}>
                {done.kind === 'export' ? 'Export ready' : 'Data deleted'}
              </Text>
            </View>
            <Text style={{ color: colors.textSec, fontSize: 14, marginBottom: 16 }}>
              {done.kind === 'export'
                ? 'We also started a download of the JSON file containing all your data.'
                : 'All records have been permanently removed from our systems. This action is final.'}
            </Text>
            <View style={{ padding: 12, backgroundColor: colors.bg, borderRadius: 10, borderColor: colors.glassBorder, borderWidth: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>
                Request ID: <Text style={{ fontFamily: Platform.select({ web: 'monospace' }) }}>{done.summary.request_id}</Text>
              </Text>
            </View>
          </View>
        ) : info ? (
          <View data-testid="privacy-verify-confirm">
            <Text style={{ color: colors.text, fontSize: 22, fontWeight: '800', marginBottom: 8 }}>
              {info.action === 'delete' ? 'Confirm data deletion' : 'Confirm data export'}
            </Text>
            <Text style={{ color: colors.textSec, fontSize: 14, marginBottom: 20 }}>
              {info.action === 'delete'
                ? 'This will permanently remove all records below. This cannot be undone.'
                : 'You\'ll get a downloadable JSON file containing all records below.'}
            </Text>

            <View style={{ borderWidth: 1, borderColor: colors.glassBorder, borderRadius: 10, overflow: 'hidden', marginBottom: 20 }}>
              {Object.entries(info.record_counts).filter(([k]) => k !== 'total').map(([k, v], i) => (
                <View key={k} data-testid={`privacy-verify-row-${k}`} style={{
                  flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
                  padding: 12, borderTopWidth: i === 0 ? 0 : 1, borderColor: colors.glassBorder,
                }}>
                  <Text style={{ color: colors.text, fontSize: 14 }}>
                    {k === 'contact_submissions' ? 'Contact form submissions'
                      : k === 'support_tickets' ? 'Support tickets'
                      : 'Feedback entries'}
                  </Text>
                  <Text style={{ color: colors.text, fontWeight: '700', fontSize: 14 }}>{v}</Text>
                </View>
              ))}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: 12, borderTopWidth: 1, borderColor: colors.glassBorder, backgroundColor: colors.bg }}>
                <Text style={{ color: colors.textSec, fontSize: 13, fontWeight: '700' }}>Total records</Text>
                <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{info.record_counts.total}</Text>
              </View>
            </View>

            {info.record_counts.total === 0 && (
              <Text style={{ color: colors.textSec, fontSize: 13, marginBottom: 16 }}>
                We don't have any data under this email.
              </Text>
            )}

            {execErr && (
              <Text data-testid="privacy-verify-exec-error" style={{ color: colors.error, marginBottom: 12 }}>{execErr}</Text>
            )}

            <TouchableOpacity
              data-testid="privacy-verify-execute"
              disabled={executing}
              onPress={execute}
              style={{
                backgroundColor: info.action === 'delete' ? colors.error : '#4F46E5',
                padding: 14, borderRadius: 10, alignItems: 'center',
                opacity: executing ? 0.6 : 1,
              }}>
              {executing ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 15 }}>
                  {info.action === 'delete' ? 'Yes, permanently delete my data' : 'Download my data'}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        ) : null}
      </View>
    </View>
  );
}
