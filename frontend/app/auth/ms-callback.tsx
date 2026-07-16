import { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet, Platform } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAuth } from '../../src/context/AuthContext';
import { getTestProps } from '../../src/utils/testProps';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

/**
 * Microsoft SSO callback page.
 * Microsoft redirects here with ?code=...&state=...
 * This page exchanges the code for a session token via XHR (no direct /api/ navigation).
 */
export default function MsCallback() {
  const { t } = useTranslation();
  t('i18n.route.auth.ms-callback.probe');
  const { colors } = useTheme();

  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    container: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg },
    card: { backgroundColor: colors.card, borderRadius: 16, padding: 32, maxWidth: 400, width: '90%', alignItems: 'center' },
    statusText: { color: colors.text, fontSize: 16, marginTop: 16, textAlign: 'center' },
    errorText: { color: colors.error, fontSize: 16, textAlign: 'center', marginBottom: 8 },
    subText: { color: colors.textMuted, fontSize: 13, textAlign: 'center' },
  });
  const router = useRouter();
  const params = useLocalSearchParams<{ code?: string; error?: string; error_description?: string }>();
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState('Signing in with Microsoft...');
  const [error, setError] = useState('');

  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code') || (params.code as string);
    const errorParam = urlParams.get('error') || (params.error as string);
    const errorDesc = urlParams.get('error_description') || (params.error_description as string);

    if (errorParam) {
      setError(`Microsoft login failed: ${errorDesc || errorParam}`);
      setTimeout(() => router.replace('/auth/login'), 3000);
      return;
    }

    if (!code) {
      setError('No authorization code received from Microsoft.');
      setTimeout(() => router.replace('/auth/login'), 3000);
      return;
    }

    // Exchange the code for a session token via XHR
    const apiBase = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.EXPO_PUBLIC_BACKEND_URL || '');
    const origin = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.REACT_APP_BACKEND_URL || process.env.EXPO_PUBLIC_BACKEND_URL || '');
    const redirectUri = `${origin}/auth/ms-callback`;

    fetch(`${apiBase}/api/auth/microsoft/exchange`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.detail || data.error || 'Token exchange failed');
        }
        return data;
      })
      .then(async (data) => {
        // Save session token to localStorage (accessible by opener/parent window)
        await AsyncStorage.setItem('session_token', data.session_token);
        if (data.refresh_token) {
          await AsyncStorage.setItem('refresh_token', data.refresh_token);
        }
        try { await AsyncStorage.setItem('last_login_method', 'microsoft'); } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

        if (Platform.OS === 'web') {
          try { localStorage.setItem('session_token', data.session_token); } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          if (data.refresh_token) {
            try { localStorage.setItem('refresh_token', data.refresh_token); } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          }
          try { localStorage.setItem('last_login_method', 'microsoft'); } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          try {
            if (window.opener && window.opener.localStorage) {
              window.opener.localStorage.setItem('session_token', data.session_token);
              if (data.refresh_token) {
                window.opener.localStorage.setItem('refresh_token', data.refresh_token);
              }
              window.opener.localStorage.setItem('last_login_method', 'microsoft');
            }
          } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          try {
            const channel = new BroadcastChannel('ms-sso');
            channel.postMessage({ type: 'ms-sso-success', token: data.session_token });
            channel.close();
          } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }

        setStatus('Login successful! Redirecting...');

        // Notify the opener window (ms-login.html) with the token directly
        if (Platform.OS === 'web') {
          const targetOrigin = (`https://${window.location.host}`);
          try {
            window.opener?.postMessage({ type: 'ms-sso-success', token: data.session_token }, targetOrigin);
          } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          // Wait to ensure localStorage write propagates before closing
          await new Promise(r => setTimeout(r, 1500));
          try { window.close(); } catch (error) { handleAppRecoverableError({ scope: 'auth/ms-callback.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
          // If window.close() didn't work, wait then redirect
          await new Promise(r => setTimeout(r, 1000));
        }

        // Refresh user context and navigate to home
        await refreshUser();
        router.replace('/');
      })
      .catch((err) => {
        console.error('MS SSO exchange error:', err);
        setError(err.message || 'Microsoft login failed. Please try again.');
        setTimeout(() => router.replace('/auth/login'), 3000);
      });
  }, [params.code, params.error, params.error_description, refreshUser, router]);

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        {error ? (
          <>
            <Text style={styles.errorText} {...getTestProps('ms-callback-error-text')}>{error}</Text>
            <Text style={styles.subText} {...getTestProps('ms-callback-redirect-text')}>{t("autofix.batch8.redirecting.to.login")}</Text>
          </>
        ) : (
          <>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={styles.statusText} {...getTestProps('ms-callback-status-text')}>{status}</Text>
          </>
        )}
      </View>
    </View>
  );
}