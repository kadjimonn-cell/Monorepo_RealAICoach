/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React, { useEffect, useMemo, useRef, useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { Animated, Easing, Image, Platform, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

const LOGO_SOURCE = require('../../../assets/images/logo.png');
const USE_NATIVE_DRIVER = Platform.OS !== 'web';

const animatedLoop = (value: Animated.Value, toValue: number, duration: number) => Animated.loop(
  Animated.sequence([
    Animated.timing(value, { toValue, duration, easing: Easing.inOut(Easing.quad), useNativeDriver: USE_NATIVE_DRIVER }),
    Animated.timing(value, { toValue: 0, duration, easing: Easing.inOut(Easing.quad), useNativeDriver: USE_NATIVE_DRIVER }),
  ])
);

export function EnterpriseBootSplash({
  visible,
  onDone,
  durationMs = 1200,
}: {
  visible: boolean;
  onDone: () => void;
  durationMs?: number;
}) {
  const [mounted, setMounted] = useState(visible);
  const opacity = useRef(new Animated.Value(0)).current;
  const logoScale = useRef(new Animated.Value(0.78)).current;
  const logoPulse = useRef(new Animated.Value(0)).current;
  const sweep = useRef(new Animated.Value(-1)).current;

  useEffect(() => {
    if (!visible) {
      Animated.timing(opacity, { toValue: 0, duration: 180, useNativeDriver: USE_NATIVE_DRIVER }).start(() => {
        setMounted(false);
      });
      return;
    }

    setMounted(true);
    opacity.setValue(0);
    logoScale.setValue(0.78);
    logoPulse.setValue(0);
    sweep.setValue(-1);

    const pulse = animatedLoop(logoPulse, 1, 980);
    const sweepAnim = Animated.loop(
      Animated.timing(sweep, {
        toValue: 1,
        duration: 1180,
        easing: Easing.inOut(Easing.cubic),
        useNativeDriver: USE_NATIVE_DRIVER,
      })
    );

    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 250, useNativeDriver: USE_NATIVE_DRIVER }),
      Animated.sequence([
        Animated.timing(logoScale, { toValue: 1.08, duration: 620, easing: Easing.out(Easing.cubic), useNativeDriver: USE_NATIVE_DRIVER }),
        Animated.timing(logoScale, { toValue: 1, duration: 460, easing: Easing.inOut(Easing.cubic), useNativeDriver: USE_NATIVE_DRIVER }),
      ]),
    ]).start();

    pulse.start();
    sweepAnim.start();

    const completeTimer = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 320, useNativeDriver: USE_NATIVE_DRIVER }).start(() => {
        pulse.stop();
        sweepAnim.stop();
        setMounted(false);
        onDone();
      });
    }, durationMs);

    return () => {
      clearTimeout(completeTimer);
      pulse.stop();
      sweepAnim.stop();
    };
  }, [visible, logoPulse, logoScale, onDone, opacity, sweep, durationMs]);

  const pulseScale = logoPulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.16] });
  const pulseOpacity = logoPulse.interpolate({ inputRange: [0, 1], outputRange: [0.32, 0.08] });
  const sweepTranslate = sweep.interpolate({ inputRange: [-1, 1], outputRange: [-230, 240] });

  if (!mounted) return null;

  return (
    <Animated.View
      style={[styles.absoluteFill, styles.bootLayer, { opacity }]}
      pointerEvents="none"
      data-testid="enterprise-boot-splash" testID="enterprise-boot-splash"
    >
      <LinearGradient
        colors={['var(--app-text)', 'var(--app-primary)', 'var(--app-primary)', 'var(--app-primary)']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={styles.absoluteFill}
      />

      <View style={styles.centerWrap}>
        <Animated.View style={[styles.outerPulse, { opacity: pulseOpacity, transform: [{ scale: pulseScale }] }]} />
        <Animated.View style={[styles.logoShell, { transform: [{ scale: logoScale }] }]}>
          <Animated.View
            style={{
              position: 'absolute',
              width: 72,
              height: 130,
              borderRadius: 30,
              transform: [{ rotate: '18deg' }, { translateX: sweepTranslate }],
              backgroundColor: 'rgba(255,255,255,0.20)',
            }}
          />
          <Image source={LOGO_SOURCE} style={styles.logo} resizeMode="contain" accessibilityLabel="RealAICoach" />
        </Animated.View>

        <Text style={styles.brandTitle} data-testid="enterprise-boot-splash-title" testID="enterprise-boot-splash-title">RealAICoach</Text>
        <Text style={styles.brandSubtitle} data-testid="enterprise-boot-splash-subtitle" testID="enterprise-boot-splash-subtitle">
          Enterprise Intelligence Platform
        </Text>
      </View>
    </Animated.View>
  );
}

export function EnterpriseTransitionOverlay({ visible }: { visible: boolean }) {
  const [mounted, setMounted] = useState(visible);
  const opacity = useRef(new Animated.Value(0)).current;
  const spin = useRef(new Animated.Value(0)).current;
  const shimmer = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      setMounted(true);
      Animated.timing(opacity, { toValue: 1, duration: 180, useNativeDriver: USE_NATIVE_DRIVER }).start();

      const spinLoop = Animated.loop(
        Animated.timing(spin, {
          toValue: 1,
          duration: 1200,
          easing: Easing.linear,
          useNativeDriver: USE_NATIVE_DRIVER,
        })
      );

      const shimmerLoop = Animated.loop(
        Animated.sequence([
          Animated.timing(shimmer, { toValue: 1, duration: 550, easing: Easing.inOut(Easing.quad), useNativeDriver: USE_NATIVE_DRIVER }),
          Animated.timing(shimmer, { toValue: 0, duration: 550, easing: Easing.inOut(Easing.quad), useNativeDriver: USE_NATIVE_DRIVER }),
        ])
      );

      spinLoop.start();
      shimmerLoop.start();

      return () => {
        spinLoop.stop();
        shimmerLoop.stop();
      };
    }

    Animated.timing(opacity, { toValue: 0, duration: 210, useNativeDriver: USE_NATIVE_DRIVER }).start(() => {
      setMounted(false);
    });
  }, [opacity, shimmer, spin, visible]);

  const spinRotation = useMemo(() => spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] }), [spin]);
  const shimmerOpacity = shimmer.interpolate({ inputRange: [0, 1], outputRange: [0.3, 1] });

  if (!mounted) return null;

  return (
    <Animated.View
      style={[styles.absoluteFill, styles.transitionLayer, { opacity }]}
      pointerEvents="none"
      data-testid="enterprise-transition-overlay" testID="enterprise-transition-overlay"
    >
      <View style={styles.transitionChip}>
        <Animated.View style={[styles.spinnerRing, { transform: [{ rotate: spinRotation }] }]} />
        <Animated.View style={[styles.logoCore, { opacity: shimmerOpacity }]}>
          <Image source={LOGO_SOURCE} style={{ width: 26, height: 26, borderRadius: 7 }} resizeMode="contain" accessibilityLabel="Decorative image" />
        </Animated.View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  absoluteFill: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  bootLayer: {
    zIndex: 1200,
  },
  centerWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  outerPulse: {
    position: 'absolute',
    width: 220,
    height: 220,
    borderRadius: 110,
    borderWidth: 1.5,
    borderColor: 'rgb(15,118,110)',
    backgroundColor: 'rgba(59,130,246,0.06)',
  },
  logoShell: {
    width: 122,
    height: 122,
    borderRadius: 34,
    borderWidth: 1,
    borderColor: 'rgba(147,197,253,0.5)',
    backgroundColor: 'rgba(0,0,0,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  logo: {
    width: 76,
    height: 76,
    borderRadius: 22,
  },
  brandTitle: {
    marginTop: 22,
    color: 'rgb(254,254,254)',
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  brandSubtitle: {
    marginTop: 8,
    color: 'rgb(175,194,235)',
    fontSize: 13,
    letterSpacing: 0.5,
    textTransform: 'uppercase',
    textAlign: 'center',
  },
  transitionLayer: {
    zIndex: 1190,
    backgroundColor: 'rgba(4,10,31,0.24)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  transitionChip: {
    width: 70,
    height: 70,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(147,197,253,0.45)',
    backgroundColor: 'rgba(0,0,0,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  spinnerRing: {
    position: 'absolute',
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 2,
    borderColor: 'rgba(125,211,252,0.35)',
    borderTopColor: 'var(--app-primary)',
  },
  logoCore: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: 'rgba(0,0,0,0.45)',
    alignItems: 'center',
    justifyContent: 'center',
  },
});

/* i18n-probe t('i18n.auto.probe') */
