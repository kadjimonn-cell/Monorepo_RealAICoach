import React, { useEffect, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { Text, StyleSheet, Platform, Animated, View, Image, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useTranslation } from '../hooks/useTranslation';
import { recordNetworkIncident } from '../services/networkIncidentTimeline';
import { useTheme } from '../context/ThemeContext';
import { shouldShowDiagnosticsBanners } from '../utils/diagnosticsVisibility';

const BRAND_LOGO = require('../../assets/images/logo.png');
const USE_NATIVE_DRIVER = Platform.OS !== 'web';
const DEGRADED_IGNORED_ENDPOINT_PATTERNS = [
  '/api/vitals/report',
  '/cdn-cgi/rum',
  '/cdn-cgi/challenge-platform',
  '/api/prompt-experiment/variant',
];

export function OfflineBanner() {
  const showDiagnosticsBanners = shouldShowDiagnosticsBanners();
  if (!showDiagnosticsBanners) return null;

  const router = useRouter();
  const { colors } = useTheme();

  // @autofix-moved: was module-level const s
  const s = StyleSheet.create({
    banner: { position: 'absolute', top: 0, left: 0, right: 0, zIndex: 9999, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 8, paddingHorizontal: 16 },
    bannerOffline: { backgroundColor: colors.warningSoft || colors.warning },
    bannerDegraded: { backgroundColor: colors.warning || colors.accent },
    bannerOnline: { backgroundColor: colors.successSoft || colors.success },
    text: { fontSize: 13, fontWeight: '600' },
    textOffline: { color: colors.warningText },
    textDegraded: { color: colors.warningText },
    textOnline: { color: colors.successText },
    diagnosticsBtn: {
      marginLeft: 8,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: 'rgba(254,240,138,0.7)',
      backgroundColor: 'rgba(0,0,0,0.25)',
      paddingHorizontal: 10,
      paddingVertical: 4,
    },
    diagnosticsText: {
      color: colors.warningText,
      fontSize: 10,
      fontWeight: '800',
    },
    reconnectWrap: {
      position: 'absolute',
      right: 20,
      bottom: 24,
      zIndex: 10000,
    },
    reconnectCard: {
      width: 220,
      borderRadius: 14,
      borderWidth: 1,
      borderColor: 'rgba(147,197,253,0.45)',
      paddingHorizontal: 14,
      paddingVertical: 12,
      alignItems: 'center',
      overflow: 'hidden',
    },
    reconnectRing: {
      position: 'absolute',
      width: 74,
      height: 74,
      borderRadius: 37,
      borderWidth: 2,
      borderColor: 'rgba(59,130,246,0.35)',
      borderTopColor: 'var(--app-primary)',
      top: 8,
    },
    reconnectLogoBox: {
      width: 48,
      height: 48,
      borderRadius: 14,
      backgroundColor: 'rgba(0,0,0,0.45)',
      borderWidth: 1,
      borderColor: 'rgba(147,197,253,0.5)',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 10,
    },
    reconnectLogo: {
      width: 32,
      height: 32,
      borderRadius: 10,
    },
    reconnectTitle: {
      color: colors.primaryText,
      fontSize: 13,
      fontWeight: '800',
      letterSpacing: 0.3,
    },
    reconnectSubtitle: {
      color: colors.textSec,
      marginTop: 3,
      fontSize: 11,
      textAlign: 'center',
    },
  });
  const [isOffline, setIsOffline] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isDegraded, setIsDegraded] = useState(false);
  const slideAnim = React.useRef(new Animated.Value(-50)).current;
  const reconnectPulse = React.useRef(new Animated.Value(0)).current;
  const reconnectSpin = React.useRef(new Animated.Value(0)).current;
  const degradedPulse = React.useRef(new Animated.Value(0)).current;
  const degradedIssuesRef = React.useRef([]);
  const degradedHideTimerRef = React.useRef(null);
  const degradedCooldownUntilRef = React.useRef(0);
  const { t } = useTranslation();

  const reconnectingLabel = t('banner.reconnecting');
  const reconnectingText = reconnectingLabel && reconnectingLabel !== 'banner.reconnecting'
    ? reconnectingLabel
    : 'Reconnecting securely...';

  useEffect(() => {
    if (Platform.OS !== 'web') return;

    const clearDegradedTimer = () => {
      if (degradedHideTimerRef.current) {
        clearTimeout(degradedHideTimerRef.current);
        degradedHideTimerRef.current = null;
      }
    };

    const triggerDegradedWarning = () => {
      if (!navigator.onLine) return;
      const now = Date.now();
      if (degradedCooldownUntilRef.current > now) return;

      setIsDegraded(true);
      recordNetworkIncident('degraded_warning', {
        source: 'offline_banner',
        issue_count_window: degradedIssuesRef.current.length,
      });

      clearDegradedTimer();
      degradedHideTimerRef.current = setTimeout(() => {
        setIsDegraded(false);
      }, 4200);

      degradedCooldownUntilRef.current = now + 30000;
      degradedIssuesRef.current = [];
    };

    const goOffline = () => {
      setIsOffline(true);
      setWasOffline(true);
      setIsDegraded(false);
      degradedIssuesRef.current = [];
      degradedCooldownUntilRef.current = 0;
      clearDegradedTimer();
      recordNetworkIncident('offline', { source: 'browser_event' });
    };

    const goOnline = () => {
      setIsOffline(false);
      setIsReconnecting(true);
      recordNetworkIncident('online_restored', { source: 'browser_event' });
      setTimeout(() => setWasOffline(false), 3000);
      setTimeout(() => setIsReconnecting(false), 1900);
    };

    const onNetworkIssue = (event: Event) => {
      if (!navigator.onLine) return;
      const detail = (event as CustomEvent)?.detail || {};
      const endpoint = String(detail.url || '');
      const isIgnoredEndpoint = DEGRADED_IGNORED_ENDPOINT_PATTERNS.some((pattern) => endpoint.includes(pattern));
      if (isIgnoredEndpoint) return;

      const now = Date.now();
      degradedIssuesRef.current = [...degradedIssuesRef.current, now].filter((ts) => (now - ts) <= 30000);
      if (degradedIssuesRef.current.length >= 3) {
        triggerDegradedWarning();
      }
    };

    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    window.addEventListener('app-network-issue', onNetworkIssue);

    if (!navigator.onLine) goOffline();

    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
      window.removeEventListener('app-network-issue', onNetworkIssue);
      clearDegradedTimer();
    };
  }, []);

  useEffect(() => {
    Animated.timing(slideAnim, {
      toValue: isOffline || wasOffline || isDegraded ? 0 : -50,
      duration: 300,
      useNativeDriver: false,
    }).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOffline, wasOffline, isDegraded]);

  useEffect(() => {
    if (!isDegraded) {
      degradedPulse.stopAnimation();
      degradedPulse.setValue(0);
      return;
    }

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(degradedPulse, { toValue: 1, duration: 380, useNativeDriver: USE_NATIVE_DRIVER }),
        Animated.timing(degradedPulse, { toValue: 0, duration: 420, useNativeDriver: USE_NATIVE_DRIVER }),
      ])
    );
    pulseLoop.start();

    return () => {
      pulseLoop.stop();
      degradedPulse.setValue(0);
    };
  }, [isDegraded, degradedPulse]);

  useEffect(() => {
    if (!isReconnecting) return;

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(reconnectPulse, { toValue: 1, duration: 420, useNativeDriver: USE_NATIVE_DRIVER }),
        Animated.timing(reconnectPulse, { toValue: 0, duration: 420, useNativeDriver: USE_NATIVE_DRIVER }),
      ])
    );

    const spinLoop = Animated.loop(
      Animated.timing(reconnectSpin, {
        toValue: 1,
        duration: 900,
        useNativeDriver: USE_NATIVE_DRIVER,
      })
    );

    pulseLoop.start();
    spinLoop.start();

    return () => {
      pulseLoop.stop();
      spinLoop.stop();
      reconnectPulse.setValue(0);
      reconnectSpin.setValue(0);
    };
  }, [isReconnecting, reconnectPulse, reconnectSpin]);

  if (!isOffline && !wasOffline && !isDegraded) return null;

  const pulseScale = reconnectPulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.08] });
  const ringOpacity = reconnectPulse.interpolate({ inputRange: [0, 1], outputRange: [0.44, 0.2] });
  const ringRotate = reconnectSpin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const degradedScale = degradedPulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.06] });

  const bannerIcon = isOffline ? 'cloud-offline' : isDegraded ? 'warning-outline' : 'cloud-done';
  const bannerText = isOffline
    ? t('banner.offline')
    : isDegraded
      ? 'Network degraded — retrying in background'
      : t('banner.backOnline');

  const openDiagnostics = () => {
    recordNetworkIncident('diagnostics_opened', { source: 'degraded_banner' });
    try {
      router.push('/ops-performance?focus=shell-health');
    } catch {
      if (typeof window !== 'undefined') {
        window.location.assign('/ops-performance?focus=shell-health');
      }
    }
  };

  return (
    <>
      <Animated.View
        style={[s.banner, isOffline ? s.bannerOffline : isDegraded ? s.bannerDegraded : s.bannerOnline, { transform: [{ translateY: slideAnim }] }]}
        data-testid={isDegraded ? 'network-degraded-banner' : 'offline-banner'} testID={isDegraded ? 'network-degraded-banner' : 'offline-banner'}
      >
        <Animated.View
          style={isDegraded ? { transform: [{ scale: degradedScale }] } : undefined}
          data-testid={isDegraded ? 'network-degraded-pulse-indicator' : undefined} testID={isDegraded ? 'network-degraded-pulse-indicator' : undefined}
        >
          <Ionicons
            name={bannerIcon}
            size={15}
            color={isOffline ? 'var(--app-primary)' : isDegraded ? 'var(--app-primary)' : 'var(--app-primary)'}
          />
        </Animated.View>
        <Text style={[s.text, isOffline ? s.textOffline : isDegraded ? s.textDegraded : s.textOnline]} data-testid={isDegraded ? 'network-degraded-banner-text' : undefined} testID={isDegraded ? 'network-degraded-banner-text' : undefined}>
          {bannerText}
        </Text>
        {isDegraded ? (
          <TouchableOpacity
            onPress={openDiagnostics}
            style={s.diagnosticsBtn}
            data-testid="network-degraded-diagnostics-button" testID="network-degraded-diagnostics-button"
          >
            <Text style={s.diagnosticsText}>Tap for diagnostics</Text>
          </TouchableOpacity>
        ) : null}
      </Animated.View>

      {isReconnecting && (
        <Animated.View
          style={[s.reconnectWrap, { transform: [{ scale: pulseScale }] }]}
          data-testid="offline-reconnect-animation" testID="offline-reconnect-animation"
        >
          <LinearGradient
            colors={[colors.text, 'var(--app-primary)', 'var(--app-primary)']}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={s.reconnectCard}
          >
            <Animated.View style={[s.reconnectRing, { opacity: ringOpacity, transform: [{ rotate: ringRotate }] }]} />
            <View style={s.reconnectLogoBox}>
              <Image source={BRAND_LOGO} style={s.reconnectLogo} resizeMode="contain" accessibilityLabel="Secure Link Restored" />
            </View>
            <Text style={s.reconnectTitle}>Secure Link Restored</Text>
            <Text style={s.reconnectSubtitle}>{reconnectingText}</Text>
          </LinearGradient>
        </Animated.View>
      )}
    </>
  );
}
