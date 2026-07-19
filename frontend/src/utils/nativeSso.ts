import { Platform } from 'react-native';
import Constants from 'expo-constants';
import api from '../services/api';

/**
 * Phase 2B — Native SSO helpers (iOS/Android builds only).
 *
 * Google: expo-auth-session authorization-code + PKCE flow.
 *   - iOS builds use GOOGLE_IOS_CLIENT_ID (reversed-client-id redirect scheme).
 *   - Android builds use GOOGLE_ANDROID_CLIENT_ID when present in backend env
 *     (drop-in later); otherwise callers fall back to the existing browser-broker flow.
 * Apple: expo-apple-authentication (iOS only).
 *
 * All provider tokens are verified server-side:
 *   POST /api/auth/google/native  { id_token }
 *   POST /api/auth/apple/native   { identity_token, full_name }
 *
 * Web behavior is untouched — every entry point returns 'unavailable' on web.
 */

export type NativeSsoResult =
  | { status: 'success'; data: Record<string, any> }
  | { status: 'unavailable'; reason: string }
  | { status: 'cancelled' }
  | { status: 'error'; message: string };

type NativeSsoConfig = {
  google_ios_client_id: string | null;
  google_android_client_id: string | null;
  apple_native_enabled: boolean;
  apple_bundle_id: string | null;
};

let cachedConfig: NativeSsoConfig | null = null;

export function isExpoGo(): boolean {
  return (
    (Constants as any)?.executionEnvironment === 'storeClient' ||
    (Constants as any)?.appOwnership === 'expo'
  );
}

export async function getNativeSsoConfig(): Promise<NativeSsoConfig | null> {
  if (cachedConfig) return cachedConfig;
  try {
    const res = await api.get('/auth/sso-config/native');
    cachedConfig = res.data as NativeSsoConfig;
    return cachedConfig;
  } catch {
    return null;
  }
}

function reversedClientIdScheme(clientId: string): string {
  // "12345-abc.apps.googleusercontent.com" -> "com.googleusercontent.apps.12345-abc"
  const suffix = '.apps.googleusercontent.com';
  if (!clientId.endsWith(suffix)) return '';
  return `com.googleusercontent.apps.${clientId.slice(0, -suffix.length)}`;
}

export async function signInWithGoogleNative(): Promise<NativeSsoResult> {
  if (Platform.OS === 'web') return { status: 'unavailable', reason: 'web' };
  if (isExpoGo()) {
    // Expo Go cannot claim custom OAuth redirect schemes; callers fall back
    // to the existing browser-broker Google flow which works in Expo Go.
    return { status: 'unavailable', reason: 'expo_go' };
  }

  const config = await getNativeSsoConfig();
  const clientId =
    Platform.OS === 'ios' ? config?.google_ios_client_id : config?.google_android_client_id;
  if (!clientId) return { status: 'unavailable', reason: 'no_client_id' };

  try {
    // Lazy require keeps native auth modules out of the web bundle.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const AuthSession = require('expo-auth-session');

    // iOS Google clients validate the reversed-client-id scheme; Android clients
    // validate package name + SHA-1 and use the package name as the scheme.
    const scheme =
      Platform.OS === 'ios' ? reversedClientIdScheme(clientId) : 'com.realaicoach.app';
    if (!scheme) return { status: 'unavailable', reason: 'bad_client_id' };
    const redirectUri = `${scheme}:/oauthredirect`;

    const discovery = {
      authorizationEndpoint: 'https://accounts.google.com/o/oauth2/v2/auth',
      tokenEndpoint: 'https://oauth2.googleapis.com/token',
    };

    const authRequest = new AuthSession.AuthRequest({
      clientId,
      redirectUri,
      scopes: ['openid', 'email', 'profile'],
      responseType: AuthSession.ResponseType.Code,
      usePKCE: true,
    });

    const result = await authRequest.promptAsync(discovery);
    if (result.type === 'cancel' || result.type === 'dismiss') return { status: 'cancelled' };
    if (result.type !== 'success' || !result.params?.code) {
      return { status: 'error', message: 'Google sign-in did not complete' };
    }

    const tokenResponse = await AuthSession.exchangeCodeAsync(
      {
        clientId,
        code: result.params.code,
        redirectUri,
        extraParams: { code_verifier: authRequest.codeVerifier || '' },
      },
      discovery,
    );

    const idToken = (tokenResponse as any)?.idToken;
    if (!idToken) return { status: 'error', message: 'Google did not return an identity token' };

    const res = await api.post('/auth/google/native', {
      id_token: idToken,
      platform: Platform.OS,
    });
    return { status: 'success', data: res.data };
  } catch (e: any) {
    return {
      status: 'error',
      message: e?.response?.data?.detail || e?.message || 'Google sign-in failed',
    };
  }
}

export async function signInWithAppleNative(): Promise<NativeSsoResult> {
  if (Platform.OS !== 'ios') return { status: 'unavailable', reason: 'ios_only' };
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const AppleAuthentication = require('expo-apple-authentication');
    const available = await AppleAuthentication.isAvailableAsync();
    if (!available) {
      // Expo Go / simulators without Apple ID support land here.
      return { status: 'unavailable', reason: 'not_supported' };
    }

    const credential = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
    });

    const identityToken = credential?.identityToken;
    if (!identityToken) return { status: 'error', message: 'Apple did not return an identity token' };

    const fullName = [credential?.fullName?.givenName, credential?.fullName?.familyName]
      .filter(Boolean)
      .join(' ');

    const res = await api.post('/auth/apple/native', {
      identity_token: identityToken,
      full_name: fullName,
    });
    return { status: 'success', data: res.data };
  } catch (e: any) {
    if (e?.code === 'ERR_REQUEST_CANCELED' || e?.code === 'ERR_CANCELED') {
      return { status: 'cancelled' };
    }
    return {
      status: 'error',
      message: e?.response?.data?.detail || e?.message || 'Apple sign-in failed',
    };
  }
}
