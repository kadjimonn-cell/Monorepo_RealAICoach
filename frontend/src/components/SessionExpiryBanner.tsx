import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, Animated, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../services/api';
import { useTranslation } from '../hooks/useTranslation';

const WARN_THRESHOLD_MS = 24 * 60 * 60 * 1000; // 24 hours before expiry
const CHECK_INTERVAL_MS = 15 * 60 * 1000; // check every 15 min

function decodeJwtExp(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    const decoded = JSON.parse(atob(payload));
    return decoded.exp ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

export default function SessionExpiryBanner() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [showBanner, setShowBanner] = useState(false);
  const [renewing, setRenewing] = useState(false);
  const [renewed, setRenewed] = useState(false);
  const [timeLeft, setTimeLeft] = useState('');
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const dismissed = useRef(false);

  const checkExpiry = useCallback(async () => {
    if (dismissed.current || renewed) return;
    try {
      const token = await AsyncStorage.getItem('session_token');
      if (!token) return;
      const expiresAt = decodeJwtExp(token);
      if (!expiresAt) return;

      const now = Date.now();
      const remaining = expiresAt - now;

      // Only show for long-lived sessions (>2 hours = "remember me" sessions)
      const totalDuration = expiresAt - (decodeJwtIat(token) || now);
      if (totalDuration < 2 * 60 * 60 * 1000) return; // skip short sessions

      if (remaining > 0 && remaining <= WARN_THRESHOLD_MS) {
        const hours = Math.floor(remaining / (60 * 60 * 1000));
        const mins = Math.floor((remaining % (60 * 60 * 1000)) / (60 * 1000));
        setTimeLeft(hours > 0 ? `${hours}h ${mins}m` : `${mins}m`);
        setShowBanner(true);
        Animated.timing(fadeAnim, { toValue: 1, duration: 300, useNativeDriver: Platform.OS !== 'web' }).start();
      } else {
        setShowBanner(false);
      }
    } catch { /* silent */ }
  }, [renewed, fadeAnim]);

  useEffect(() => {
    if (!user) return;
    checkExpiry();
    const interval = setInterval(checkExpiry, CHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [user, checkExpiry]);

  const handleRenew = useCallback(async () => {
    setRenewing(true);
    try {
      const res = await api.post('/auth/renew-session');
      const { session_token, refresh_token } = res.data;
      if (session_token) {
        await AsyncStorage.setItem('session_token', session_token);
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          window.localStorage.setItem('session_token', session_token);
        }
      }
      if (refresh_token) await AsyncStorage.setItem('refresh_token', refresh_token);
      setRenewed(true);
      setTimeout(() => {
        Animated.timing(fadeAnim, { toValue: 0, duration: 300, useNativeDriver: Platform.OS !== 'web' }).start(() => setShowBanner(false));
      }, 2000);
    } catch {
      /* silent — user can try again */
    } finally {
      setRenewing(false);
    }
  }, [fadeAnim]);

  const handleDismiss = useCallback(() => {
    dismissed.current = true;
    Animated.timing(fadeAnim, { toValue: 0, duration: 200, useNativeDriver: Platform.OS !== 'web' }).start(() => setShowBanner(false));
  }, [fadeAnim]);

  if (!showBanner || !user) return null;

  const bg = renewed ? colors.successSoft : colors.warningSoft;
  const border = renewed ? colors.successSoft : colors.warningSoft;
  const accent = renewed ? colors.success : colors.warning;

  return (
    <Animated.View
      style={{
        opacity: fadeAnim,
        marginHorizontal: 16, marginBottom: 8, borderRadius: 12,
        backgroundColor: bg, borderWidth: 1, borderColor: border,
        paddingVertical: 12, paddingHorizontal: 16,
        flexDirection: 'row', alignItems: 'center', gap: 12,
      }}
      data-testid="session-expiry-banner" testID="session-expiry-banner"
    >
      <Ionicons name={renewed ? 'checkmark-circle' : 'time-outline'} size={22} color={accent} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700' }} data-testid="session-expiry-title" testID="session-expiry-title">
          {renewed ? t('session.renewed') : t('session.expiringSoon')}
        </Text>
        <Text style={{ color: colors.textSecondary || 'var(--app-primary)', fontSize: 11, marginTop: 2 }} data-testid="session-expiry-message" testID="session-expiry-message">
          {renewed
            ? t('session.renewedMsg')
            : t('session.expiringMsg').replace('{time}', timeLeft)}
        </Text>
      </View>
      {!renewed && (
        <TouchableOpacity accessibilityLabel="Session renew button"
          onPress={handleRenew}
          disabled={renewing}
          style={{
            backgroundColor: accent, borderRadius: 8,
            paddingHorizontal: 14, paddingVertical: 7,
            opacity: renewing ? 0.6 : 1,
          }}
          data-testid="session-renew-button" testID="session-renew-button"
        >
          <Text style={{ color: colors.primaryText || colors.buttonText || colors.text, fontSize: 12, fontWeight: '700' }}>
            {renewing ? t('session.renewing') : t('session.staySignedIn')}
          </Text>
        </TouchableOpacity>
      )}
      <TouchableOpacity onPress={handleDismiss} data-testid="session-expiry-dismiss" testID="session-expiry-dismiss">
        <Ionicons name="close" size={18} color={colors.textSecondary || 'var(--app-primary)'} />
      </TouchableOpacity>
    </Animated.View>
  );
}

function decodeJwtIat(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    const decoded = JSON.parse(atob(payload));
    return decoded.iat ? decoded.iat * 1000 : null;
  } catch {
    return null;
  }
}
