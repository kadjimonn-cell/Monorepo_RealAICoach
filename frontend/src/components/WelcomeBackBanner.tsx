import React, { useEffect, useState, useRef } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, Animated, Platform, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useTranslation } from '../hooks/useTranslation';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

const ROUTE_LABELS: Record<string, { label: string; icon: string }> = {
  '/': { label: 'Home', icon: 'home' },
  '/index': { label: 'Home', icon: 'home' },
  '/progress': { label: 'Progress', icon: 'bar-chart' },
  '/profile': { label: 'Profile', icon: 'person' },
  '/ai-learning-hub': { label: 'AI Learning Hub', icon: 'school' },
  '/ai-coaching-team': { label: 'AI Coaching Team', icon: 'people-circle' },
  '/ai-lifecoach': { label: 'AI Life Coach', icon: 'chatbubbles' },
  '/ai-goals': { label: 'AI Goals', icon: 'flag' },
  '/ai-documents': { label: 'AI Documents', icon: 'document-text' },
  '/feature-gallery': { label: 'AI Feature Gallery', icon: 'grid' },
  '/mini-apps': { label: 'Features', icon: 'grid' },
  '/hiring-hub': { label: 'Hiring Hub', icon: 'briefcase' },
  '/payment-history': { label: 'Payment History', icon: 'receipt' },
  '/subscription/plans': { label: 'Subscription Plans', icon: 'card' },
  '/settings': { label: 'Settings', icon: 'settings' },
  '/help': { label: 'Help Center', icon: 'help-circle' },
  '/my-tickets': { label: 'Support Tickets', icon: 'chatbox-ellipses' },
  '/executive-dashboard': { label: 'Executive Dashboard', icon: 'shield-checkmark' },
};

function getRouteInfo(route: string): { label: string; icon: string } | null {
  if (!route || route === '/' || route === '/index') return null; // Don't show resume for home
  const exact = ROUTE_LABELS[route];
  if (exact) return exact;
  // Fuzzy match
  for (const [key, val] of Object.entries(ROUTE_LABELS)) {
    if (route.includes(key.slice(1)) && key !== '/') return val;
  }
  // Fallback: clean up route name
  const cleaned = route.replace(/^\//, '').replace(/-/g, ' ').replace(/\//g, ' > ');
  if (cleaned && cleaned !== 'index') {
    return { label: cleaned.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '), icon: 'arrow-forward-circle' };
  }
  return null;
}

function getTimeSince(isoDate?: string): string {
  if (!isoDate) return '';
  try {
    const last = new Date(isoDate).getTime();
    const now = Date.now();
    const diffMs = now - last;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} minute${mins > 1 ? 's' : ''} ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs} hour${hrs > 1 ? 's' : ''} ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
    const months = Math.floor(days / 30);
    return `${months} month${months > 1 ? 's' : ''} ago`;
  } catch { return ''; }
}

export default function WelcomeBackBanner() {
  const { welcomeBack, clearWelcomeBack, user } = useAuth();
   
  const {darkMode, colors} = useTheme();
  const router = useRouter();
  const [fadeAnim] = useState(new Animated.Value(0));
  const [scaleAnim] = useState(new Animated.Value(0.85));
  const [overlayBlocking, setOverlayBlocking] = useState(false);
  const clearRef = useRef(clearWelcomeBack);
  clearRef.current = clearWelcomeBack;
  const { t } = useTranslation();

  const routeInfo = welcomeBack?.lastRoute ? getRouteInfo(welcomeBack.lastRoute) : null;
  const dismissalKey = user?.user_id ? `welcome_back_dismissed:${user.user_id}` : null;

  const dismissBanner = React.useCallback(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined' && dismissalKey && welcomeBack) {
      try {
        const marker = `${welcomeBack.lastRoute || ''}|${welcomeBack.lastActiveAt || ''}`;
        window.sessionStorage.setItem(dismissalKey, marker);
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/WelcomeBackBanner.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
    clearWelcomeBack();
  }, [clearWelcomeBack, dismissalKey, welcomeBack]);

  // Expose dismiss function globally for automated testing (uses ref for stable reference)
  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      (window as any).__dismissWelcomeBack = () => { clearRef.current(); return true; };
    }
    return () => {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        delete (window as any).__dismissWelcomeBack;
      }
    };
  }, []);

  useEffect(() => {
    if (welcomeBack) {
      const lastRoute = (welcomeBack.lastRoute || '').toLowerCase();
      const skipBlockingBanner = lastRoute.startsWith('/executive-dashboard');
      if (skipBlockingBanner) {
        setOverlayBlocking(false);
        clearWelcomeBack();
        return;
      }

      setOverlayBlocking(true);
      if (Platform.OS === 'web' && typeof window !== 'undefined' && dismissalKey) {
        try {
          const marker = `${welcomeBack.lastRoute || ''}|${welcomeBack.lastActiveAt || ''}`;
          const dismissedMarker = window.sessionStorage.getItem(dismissalKey);
          if (dismissedMarker && dismissedMarker === marker) {
            clearWelcomeBack();
            return;
          }
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/WelcomeBackBanner.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }

      Animated.parallel([
        Animated.spring(scaleAnim, { toValue: 1, friction: 6, tension: 80, useNativeDriver: Platform.OS !== 'web' }),
        Animated.timing(fadeAnim, { toValue: 1, duration: 350, useNativeDriver: Platform.OS !== 'web' }),
      ]).start();

      const visibleMs = routeInfo ? 8000 : 4500;
      const timer = setTimeout(() => {
        setOverlayBlocking(false);
        Animated.parallel([
          Animated.timing(fadeAnim, { toValue: 0, duration: 400, useNativeDriver: Platform.OS !== 'web' }),
          Animated.timing(scaleAnim, { toValue: 0.9, duration: 400, useNativeDriver: Platform.OS !== 'web' }),
        ]).start(() => dismissBanner());
      }, visibleMs);

      const failSafeDismiss = setTimeout(() => {
        setOverlayBlocking(false);
        dismissBanner();
      }, visibleMs + 1200);

      return () => {
        clearTimeout(timer);
        clearTimeout(failSafeDismiss);
      };
    }
    setOverlayBlocking(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [welcomeBack, dismissalKey, dismissBanner]);

  if (!welcomeBack) return null;

  const timeSince = getTimeSince(welcomeBack.lastActiveAt);
  const avatarUrl = user?.profile_image || user?.picture;
  const initials = (welcomeBack.name || '?').charAt(0).toUpperCase();

  return (
    <Animated.View
      pointerEvents={overlayBlocking ? 'box-none' : 'none'}
      data-testid="welcome-back-overlay" testID="welcome-back-overlay"
      style={{
        opacity: fadeAnim,
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        zIndex: 99999,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: darkMode ? 'rgba(5,10,20,0.7)' : 'rgba(0,0,0,0.35)',
        ...(Platform.OS === 'web' ? { backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)' } as any : {}),
      }}
    >
      <Animated.View
        data-testid="welcome-back-card" testID="welcome-back-card"
        style={{
          transform: [{ scale: scaleAnim }],
          width: 320,
          maxWidth: '90%',
          borderRadius: 24,
          overflow: 'hidden' as const,
          borderWidth: 1,
          borderColor: 'rgba(16,185,129,0.25)',
          ...(Platform.OS === 'web' ? { boxShadow: '0 24px 64px rgba(0,0,0,0.5), 0 0 0 1px rgba(16,185,129,0.1)' } : {}),
        }}
      >
        {/* Gradient top bar */}
        <View style={{ height: 4, backgroundColor: colors.success }} />

        <View style={{
          backgroundColor: darkMode ? 'rgba(11,18,33,0.95)' : 'rgba(255,255,255,0.96)',
          padding: 28,
          alignItems: 'center',
          ...(Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}),
        }}>
          {/* Avatar */}
          <View style={{
            width: 72, height: 72, borderRadius: 36,
            borderWidth: 2.5, borderColor: colors.success,
            alignItems: 'center', justifyContent: 'center',
            marginBottom: 16,
            overflow: 'hidden' as const,
            backgroundColor: 'rgba(16,185,129,0.15)',
          }}>
            {avatarUrl ? (
              Platform.OS === 'web' ? (
                <img src={avatarUrl} style={{ width: 72, height: 72, borderRadius: 36, objectFit: 'cover' } as any} alt="" />
              ) : (
                <Image source={{ uri: avatarUrl }} style={{ width: 72, height: 72, borderRadius: 36 }} accessibilityLabel="initials" />
              )
            ) : (
              <Text style={{ color: colors.successText, fontSize: 28, fontWeight: '800' }}>{initials}</Text>
            )}
          </View>

          {/* Welcome text */}
          <Text testID="welcome-back-title" style={{
            color: colors.primaryText, fontSize: 20, fontWeight: '700',
            textAlign: 'center', letterSpacing: -0.3,
          }}>
            Welcome back, {welcomeBack.name}!
          </Text>

          {/* Time since */}
          {timeSince ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', marginTop: 8, gap: 6 }}>
              <Ionicons name="time-outline" size={14} color="rgba(255,255,255,0.5)" />
              <Text testID="welcome-back-time" style={{
                color: 'rgba(255,255,255,0.5)', fontSize: 13,
                fontWeight: '500',
              }}>
                {t('welcomeBack.lastSession')} {timeSince}
              </Text>
            </View>
          ) : null}

          {/* Buttons */}
          <View style={{ marginTop: 20, gap: 10, width: '100%' }}>
            {/* Quick Resume - only shown when there's a meaningful last route */}
            {routeInfo && (
              <TouchableOpacity accessibilityLabel="Welcome back quick resume button"
                testID="welcome-back-quick-resume"
                onPress={() => {
                  dismissBanner();
                  router.push(welcomeBack!.lastRoute as any);
                }}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  paddingVertical: 12,
                  paddingHorizontal: 20,
                  borderRadius: 12,
                  backgroundColor: colors.success,
                }}
              >
                <Ionicons name={routeInfo.icon as any} size={16} color="var(--app-primary-text)" />
                <Text style={{ color: colors.primaryText, fontSize: 14, fontWeight: '700', letterSpacing: 0.3 }}>
                  {t('welcomeBack.resume')} {routeInfo.label}
                </Text>
                <Ionicons name="arrow-forward" size={14} color="rgba(255,255,255,0.7)" />
              </TouchableOpacity>
            )}

            {/* Continue / Dismiss */}
            <TouchableOpacity accessibilityLabel="Welcome back dismiss button"
              testID="welcome-back-dismiss"
              onPress={dismissBanner}
              {...(Platform.OS === 'web' ? { id: 'welcome-back-dismiss' } as any : {})}
              style={{
                paddingVertical: routeInfo ? 9 : 10,
                paddingHorizontal: 28,
                borderRadius: 12,
                backgroundColor: routeInfo ? 'transparent' : colors.success,
                borderWidth: routeInfo ? 1 : 0,
                borderColor: darkMode ? 'rgba(255,255,255,0.20)' : 'rgba(0,0,0,0.12)',
                alignItems: 'center',
              }}
            >
              <Text style={{
                color: routeInfo ? (darkMode ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.5)') : 'var(--app-primary-text)',
                fontSize: routeInfo ? 13 : 14,
                fontWeight: '600',
                letterSpacing: 0.3,
              }}>
                {routeInfo ? t('welcomeBack.goHome') : t('welcomeBack.continue')}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </Animated.View>
    </Animated.View>
  );
}
