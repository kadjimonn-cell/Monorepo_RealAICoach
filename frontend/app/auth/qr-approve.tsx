import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../../src/services/api';
import { ProfileFormSkeleton } from '../../src/components/SkeletonLoaders';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

import { useAdminTheme } from '../../src/hooks/useAdminTheme';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function QRApprovePage() {
  const { t } = useTranslation();
  t('i18n.route.auth.qr-approve.probe');
  const AC = useAdminTheme();
  const T = {
    bg: AC.bg, card: AC.cardBg || AC.surfaceElevated || '#111B30', cyan: '#00F0FF', green: '#00FF94',
    red: '#FF2E2E', white: AC.text, onPrimary: AC.primaryText || AC.buttonText || AC.text, text2: AC.textMuted, text3: AC.textDim,
    border: AC.border || 'rgba(255,255,255,0.1)',
  };
  const { session } = useLocalSearchParams<{ session: string }>();
  const router = useRouter();
  const [status, setStatus] = useState<'loading' | 'ready' | 'approved' | 'error' | 'expired'>('loading');
  const [error, setError] = useState('');
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    if (!session) {
      setStatus('error');
      setError('No QR session ID provided');
      return;
    }
    // Check if user is logged in — on web, auth is cookie-based (not AsyncStorage)
    (async () => {
      let isAuthenticated = false;
      if (Platform.OS === 'web') {
        // Web uses HttpOnly cookie auth — verify by calling /auth/me
        try {
          const meRes = await api.get('/auth/me');
          isAuthenticated = !!(meRes.data && meRes.data.user_id);
        } catch {
          isAuthenticated = false;
        }
      } else {
        // Native/mobile uses AsyncStorage token
        const token = await AsyncStorage.getItem('session_token');
        isAuthenticated = !!token;
      }
      if (!isAuthenticated) {
        setStatus('error');
        setError('You must be logged in on this device to approve the QR login. Please sign in first.');
        return;
      }
      // Verify session exists and is pending
      try {
        const res = await api.get(`/auth/qr/status/${session}`);
        if (res.data.status === 'pending') {
          setStatus('ready');
        } else if (res.data.status === 'expired') {
          setStatus('expired');
        } else {
          setStatus('error');
          setError(`QR session is ${res.data.status}`);
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'auth.qr-approve.verify-session',
          error,
          message: 'QR session not found or expired',
          setError,
          onRetry: () => { if (session) { void api.get(`/auth/qr/status/${session}`); } },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setStatus('error');
        setError('QR session not found or expired');
      }
    })();
  }, [session]);

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.post('/auth/qr/approve', { session_id: session });
      setStatus('approved');
    } catch (e: any) {
      handleAppRecoverableError({
        scope: 'auth.qr-approve.submit-approval',
        error: e,
        message: e?.response?.data?.detail || 'Approval failed',
        setError,
        onRetry: () => { void handleApprove(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setError(e?.response?.data?.detail || 'Approval failed');
      setStatus('error');
    }
    setApproving(false);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: T.bg }} data-testid="qr-approve-screen" testID="qr-approve-screen">
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        {status === 'loading' && (
          <ProfileFormSkeleton />
        )}

        {status === 'ready' && (
          <View style={{ backgroundColor: T.card, borderRadius: 20, padding: 32, alignItems: 'center', maxWidth: 380, width: '100%', borderWidth: 1, borderColor: T.border }} data-testid="qr-approve-card" testID="qr-approve-card">
            <View style={{ width: 64, height: 64, borderRadius: 32, backgroundColor: (globalThis as any).__alphaColor(T.cyan, '15'), justifyContent: 'center', alignItems: 'center', marginBottom: 20 }}>
              <Ionicons name="desktop-outline" size={32} color={T.cyan} />
            </View>
            <Text style={{ color: T.white, fontSize: 20, fontWeight: '800', marginBottom: 8 }}>Desktop Login Request</Text>
            <Text style={{ color: T.text2, fontSize: 13, textAlign: 'center', marginBottom: 24, lineHeight: 20 }}>
              A desktop browser is requesting to sign in to your account. Tap "Approve" to grant access.
            </Text>
            <View style={{ backgroundColor: (globalThis as any).__alphaColor(T.cyan, '08'), borderRadius: 12, padding: 12, width: '100%', marginBottom: 24, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '20') }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="shield-checkmark" size={16} color={T.cyan} />
                <Text style={{ color: T.cyan, fontSize: 11, fontWeight: '600' }}>Session ID: {session?.slice(0, 12)}...</Text>
              </View>
            </View>
            <TouchableOpacity
              onPress={handleApprove}
              disabled={approving}
              style={{ width: '100%', paddingVertical: 14, borderRadius: 12, alignItems: 'center', opacity: approving ? 0.6 : 1, overflow: 'hidden' }}
              data-testid="qr-approve-button" testID="qr-approve-button"
            >
              {Platform.OS === 'web' ? (
                <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(135deg, ${T.cyan}, ${AC.primary})`, borderRadius: 12 }} />
              ) : (
                <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: T.cyan, borderRadius: 12 }} />
              )}
              {approving ? (
                <ActivityIndicator color={T.onPrimary} />
              ) : (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="checkmark-circle" size={18} color={T.onPrimary} />
                  <Text style={{ color: T.onPrimary, fontSize: 15, fontWeight: '800' }}>APPROVE LOGIN</Text>
                </View>
              )}
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.back()} style={{ marginTop: 16 }} data-testid="qr-deny-button" testID="qr-deny-button">
              <Text style={{ color: T.text3, fontSize: 13 }}>Deny</Text>
            </TouchableOpacity>
          </View>
        )}

        {status === 'approved' && (
          <View style={{ alignItems: 'center', gap: 16 }} data-testid="qr-approve-success" testID="qr-approve-success">
            <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: (globalThis as any).__alphaColor(T.green, '18'), justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: (globalThis as any).__alphaColor(T.green, '40') }}>
              <Ionicons name="checkmark" size={36} color={T.green} />
            </View>
            <Text style={{ color: T.white, fontSize: 20, fontWeight: '800' }}>Login Approved!</Text>
            <Text style={{ color: T.text2, fontSize: 13, textAlign: 'center' }}>The desktop browser will log in automatically. You can close this page.</Text>
            <TouchableOpacity onPress={() => router.replace('/dashboard')} style={{ marginTop: 16, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '40') }}>
              <Text style={{ color: T.cyan, fontSize: 13, fontWeight: '700' }}>Back to App</Text>
            </TouchableOpacity>
          </View>
        )}

        {status === 'expired' && (
          <View style={{ alignItems: 'center', gap: 16 }}>
            <Ionicons name="time-outline" size={48} color={T.text3} />
            <Text style={{ color: T.white, fontSize: 18, fontWeight: '700' }}>QR Session Expired</Text>
            <Text style={{ color: T.text2, fontSize: 13, textAlign: 'center' }}>Please generate a new QR code on the desktop login page.</Text>
          </View>
        )}

        {status === 'error' && (
          <View style={{ alignItems: 'center', gap: 16 }} data-testid="qr-approve-error" testID="qr-approve-error">
            <Ionicons name="alert-circle" size={48} color={T.red} />
            <Text style={{ color: T.white, fontSize: 18, fontWeight: '700' }}>Error</Text>
            <Text style={{ color: T.text2, fontSize: 13, textAlign: 'center' }}>{error}</Text>
            <TouchableOpacity onPress={() => router.replace('/auth/login')} style={{ marginTop: 8, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.cyan, '40') }}>
              <Text style={{ color: T.cyan, fontSize: 13, fontWeight: '700' }}>Go to Login</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}