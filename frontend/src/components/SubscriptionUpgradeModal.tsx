import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Modal,
  Animated, Dimensions, Platform, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useSubscription } from '../context/SubscriptionContext';
import { useABVariant } from '../hooks/useABVariant';
import { notificationEvents } from '../utils/notificationEvents';
import api from '../services/api';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { getFrontendPlanName, getFrontendPlanPrice } from '../config/pricingPolicy';

// ── Inline contrast color helper (avoids Metro resolution issues) ──
type Rgb = { r: number; g: number; b: number };

const CSS_VAR_FALLBACKS: Record<string, string> = {
  '--app-primary': '#0F766E',
  '--app-primary-text': '#FFFFFF',
  '--app-text': '#0F172A',
  '--app-warning': '#D97706',
  '--app-success': '#16A34A',
  '--app-error': '#DC2626',
  '--app-info': '#0284C7',
};

const resolveCssVar = (input: string): string => {
  const match = String(input || '').trim().match(/^var\((--[^,)\s]+)(?:\s*,\s*([^\)]+))?\)$/i);
  if (!match) return String(input || '').trim();
  const varName = match[1];
  const inlineFallback = String(match[2] || '').trim();

  if (typeof document !== 'undefined') {
    const runtimeValue = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
    if (runtimeValue) return runtimeValue;
  }

  return inlineFallback || CSS_VAR_FALLBACKS[varName] || input;
};

const parseRgb = (raw: string): Rgb | null => {
  const color = resolveCssVar(raw);
  const hex = color.replace('#', '').trim();

  if (/^[0-9a-f]{3}$/i.test(hex)) {
    return {
      r: Number.parseInt(hex[0] + hex[0], 16),
      g: Number.parseInt(hex[1] + hex[1], 16),
      b: Number.parseInt(hex[2] + hex[2], 16),
    };
  }

  if (/^[0-9a-f]{6}$/i.test(hex)) {
    return {
      r: Number.parseInt(hex.slice(0, 2), 16),
      g: Number.parseInt(hex.slice(2, 4), 16),
      b: Number.parseInt(hex.slice(4, 6), 16),
    };
  }

  const rgbMatch = color.match(/^rgba?\(([^)]+)\)$/i);
  if (!rgbMatch) return null;
  const parts = rgbMatch[1].split(',').map((p) => Number.parseFloat(p.trim()));
  if (parts.length < 3 || parts.slice(0, 3).some((v) => Number.isNaN(v))) return null;
  return { r: parts[0], g: parts[1], b: parts[2] };
};

const channelLuminance = (value: number) => {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
};

const getReadableTextColor = (
  backgroundColor: string,
  options?: { light?: string; dark?: string; threshold?: number },
) => {
  const light = options?.light || 'var(--app-primary-text)';
  const dark = options?.dark || 'var(--app-text)';
  const threshold = typeof options?.threshold === 'number' ? options.threshold : 0.56;

  const rgb = parseRgb(backgroundColor);
  if (!rgb) return light;

  const luminance =
    0.2126 * channelLuminance(rgb.r) +
    0.7152 * channelLuminance(rgb.g) +
    0.0722 * channelLuminance(rgb.b);

  return luminance > threshold ? dark : light;
};

// ── Event bus for subscription upgrade triggers ──
type UpgradePayload = {
  requiredPlan: string;
  currentPlan: string;
  message: string;
  endpoint?: string;
  method?: string;
  source?: 'auto_api' | 'manual' | string;
};

type Listener = (payload: UpgradePayload) => void;
const listeners: Set<Listener> = new Set();
const PLAN_RANK: Record<string, number> = { free: 0, basic: 1, premium: 2 };

// Buffer concurrent 403s and pick the highest required plan
let pendingPayload: UpgradePayload | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;

export const subscriptionUpgradeEmitter = {
  emit: (payload: UpgradePayload) => {
    const incomingRank = PLAN_RANK[payload.requiredPlan] ?? 1;
    const currentRank = pendingPayload ? (PLAN_RANK[pendingPayload.requiredPlan] ?? 0) : -1;
    if (incomingRank > currentRank) {
      pendingPayload = payload;
    }
    if (flushTimer) clearTimeout(flushTimer);
    flushTimer = setTimeout(() => {
      if (pendingPayload) {
        listeners.forEach(fn => fn(pendingPayload!));
        pendingPayload = null;
      }
      flushTimer = null;
    }, 300);
  },
  subscribe: (fn: Listener) => {
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  },
};

// ── Plan data ──

const PLAN_LEVEL: Record<string, number> = { free: 0, basic: 1, premium: 2 };

export default function SubscriptionUpgradeModal() {
  const [visible, setVisible] = useState(false);
  const [payload, setPayload] = useState<UpgradePayload | null>(null);
  const { colors } = useTheme();

  // @autofix-moved: was module-level const PLANS
  const PLANS = [
    {
      id: 'free',
      name: getFrontendPlanName('free'),
      price: `$${getFrontendPlanPrice('free', 'monthly').toFixed(2).replace('.00', '')}`,
      icon: 'person-outline' as const,
      color: colors.textMuted,
      features: ['3 AI conversations/day', 'Basic scenarios', 'Community support'],
    },
    {
      id: 'basic',
      name: getFrontendPlanName('basic'),
      price: `$${getFrontendPlanPrice('basic', 'monthly').toFixed(2)}`,
      icon: 'star' as const,
      color: colors.primary,
      features: ['10 conversations/day', 'All scenarios', 'Progress tracking', 'Email support', 'PDF exports'],
    },
    {
      id: 'premium',
      name: getFrontendPlanName('premium'),
      price: `$${getFrontendPlanPrice('premium', 'monthly').toFixed(2)}`,
      icon: 'diamond' as const,
      color: colors.warningText,
      features: ['Unlimited conversations', 'Advanced analytics', 'AI improvement plans', 'Priority support', 'All features unlocked'],
    },
  ];
  // @autofix-moved: was module-level const styles
  const styles = StyleSheet.create({
    overlay: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.55)',
      justifyContent: 'center',
      alignItems: 'center',
    },
    container: {
      width: MODAL_W,
      maxHeight: '85%',
      borderRadius: 20,
      paddingHorizontal: 24,
      paddingTop: 28,
      paddingBottom: 20,
      ...(Platform.OS === 'web' ? { boxShadow: '0 24px 48px rgba(0,0,0,0.18)' } : {}),
    },
    closeBtn: {
      position: 'absolute',
      top: 0,
      right: 0,
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10,
    },
    lockCircle: {
      width: 56,
      height: 56,
      borderRadius: 28,
      alignItems: 'center',
      justifyContent: 'center',
      alignSelf: 'center',
      marginBottom: 14,
    },
    title: {
      fontSize: 20,
      fontWeight: '700',
      textAlign: 'center',
      letterSpacing: -0.3,
    },
    subtitle: {
      fontSize: 14,
      textAlign: 'center',
      marginTop: 6,
      marginBottom: 20,
      lineHeight: 20,
      paddingHorizontal: 8,
    },
    plansRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 10,
      marginBottom: 18,
    },
    planCard: {
      flex: 1,
      borderRadius: 14,
      borderWidth: 1.5,
      paddingVertical: 14,
      paddingHorizontal: 10,
      alignItems: 'center',
      minHeight: 110,
      justifyContent: 'center',
    },
    planCardCurrent: {
      opacity: 0.7,
    },
    planCardRequired: {
      borderWidth: 2,
      position: 'relative',
      overflow: 'visible',
    },
    planLabel: {
      fontSize: 10,
      fontWeight: '600',
      textTransform: 'uppercase',
      letterSpacing: 0.8,
      marginBottom: 6,
    },
    planIconCircle: {
      width: 34,
      height: 34,
      borderRadius: 17,
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 6,
    },
    planName: {
      fontSize: 15,
      fontWeight: '700',
    },
    planPrice: {
      fontSize: 18,
      fontWeight: '800',
      marginTop: 2,
    },
    planPeriod: {
      fontSize: 12,
      fontWeight: '500',
    },
    arrowContainer: {
      paddingHorizontal: 2,
    },
    recommendBadge: {
      position: 'absolute',
      top: -10,
      paddingHorizontal: 10,
      paddingVertical: 3,
      borderRadius: 10,
    },
    recommendText: {
      color: colors.primaryText,
      fontSize: 10,
      fontWeight: '700',
      textTransform: 'uppercase',
      letterSpacing: 0.5,
    },
    featuresBox: {
      borderRadius: 12,
      borderWidth: 1,
      padding: 14,
      marginBottom: 18,
    },
    featuresTitle: {
      fontSize: 13,
      fontWeight: '700',
      marginBottom: 10,
    },
    featureRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      marginBottom: 7,
    },
    featureText: {
      fontSize: 13,
      lineHeight: 18,
    },
    upgradeBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      paddingVertical: 14,
      borderRadius: 12,
      marginBottom: 8,
    },
    upgradeBtnText: {
      color: colors.primaryText,
      fontSize: 15,
      fontWeight: '700',
    },
    laterBtn: {
      paddingVertical: 10,
      alignItems: 'center',
    },
    laterBtnText: {
      fontSize: 13,
      fontWeight: '500',
    },
  });
  const router = useRouter();
  const { plan: currentPlan } = useSubscription();
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(50)).current;
  const cooldownRef = useRef(false);
  const nativeSessionShownRef = useRef<Record<string, boolean>>({});

  // A/B testing integration
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { getConfig, trackEvent, isActive: _hasABTest } = useABVariant('upgrade_modal');

  const show = useCallback((p: UpgradePayload) => {
    if (cooldownRef.current) return;

    // Guardrail policy: For Free/Basic users, auto API-triggered upgrade modal
    // should appear at most once per login session.
    const plan = String(p?.currentPlan || 'free').toLowerCase();
    const isGuardedPlan = plan === 'free' || plan === 'basic';
    const isAutoApiPrompt = (p?.source || 'auto_api') === 'auto_api';
    let telemetrySessionKey = `native:${plan}`;
    if (isGuardedPlan && isAutoApiPrompt) {
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        try {
          const sessionToken = window.localStorage.getItem('session_token') || 'anon';
          telemetrySessionKey = sessionToken;
          const onceKey = `subscription-upgrade-shown:${sessionToken}:${plan}`;
          if (window.sessionStorage.getItem(onceKey) === '1') {
            return;
          }
          window.sessionStorage.setItem(onceKey, '1');
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/SubscriptionUpgradeModal.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      } else {
        const onceKey = `${plan}:auto`;
        if (nativeSessionShownRef.current[onceKey]) {
          return;
        }
        nativeSessionShownRef.current[onceKey] = true;
      }
    }

    cooldownRef.current = true;
    setTimeout(() => { cooldownRef.current = false; }, 3000);
    setPayload(p);
    setVisible(true);

    // Non-blocking telemetry for admin watchdog dashboards.
    void api.post('/subscription-prompt/telemetry', {
      session_key: telemetrySessionKey,
      current_plan: plan,
      required_plan: String(p.requiredPlan || 'basic').toLowerCase(),
      source: p.source || 'auto_api',
      endpoint: p.endpoint || null,
      route: (typeof window !== 'undefined' ? window.location?.pathname : null) || null,
    }, { silentLoading: true }).catch(() => undefined);
  }, []);

  useEffect(() => {
    const unsub = subscriptionUpgradeEmitter.subscribe(show);
    return unsub;
  }, [show]);

  useEffect(() => {
    if (visible) {
      fadeAnim.setValue(0);
      slideAnim.setValue(50);
      Animated.parallel([
        Animated.timing(fadeAnim, { toValue: 1, duration: 250, useNativeDriver: true }),
        Animated.spring(slideAnim, { toValue: 0, tension: 65, friction: 9, useNativeDriver: true }),
      ]).start();
      // Track A/B impression
      trackEvent('impression', { plan: payload?.requiredPlan });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const close = useCallback(() => {
    trackEvent('dismiss', { plan: payload?.requiredPlan });
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 0, duration: 180, useNativeDriver: true }),
      Animated.timing(slideAnim, { toValue: 80, duration: 180, useNativeDriver: true }),
    ]).start(() => setVisible(false));
  }, [fadeAnim, slideAnim, trackEvent, payload]);

  useEffect(() => {
    const unsubscribe = notificationEvents.on('whats-new-visibility', (isOpen) => {
      if (isOpen && visible) {
        close();
      }
    });
    return unsubscribe;
  }, [close, visible]);

  const handleUpgrade = useCallback(() => {
    trackEvent('click', { plan: payload?.requiredPlan });
    close();
    setTimeout(() => router.push('/subscription/plans'), 200);
  }, [close, router, trackEvent, payload]);

  if (!visible || !payload) return null;

  const requiredPlanData = PLANS.find(p => p.id === payload.requiredPlan) || PLANS[1];
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _userLevel = PLAN_LEVEL[currentPlan || 'free'] ?? 0;

  const sanitizeCtaText = (rawValue: any, fallback: string) => {
    const normalized = String(rawValue ?? '').trim();
    return normalized.length > 0 ? normalized : fallback;
  };

  const sanitizeCtaColor = (rawValue: any, fallback: string) => {
    const normalized = String(rawValue ?? '').trim();
    if (!normalized) return fallback;
    if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(normalized)) return normalized;
    if (/^rgba?\(/i.test(normalized)) return normalized;
    if (/^var\(--app-[a-z0-9-]+\)$/i.test(normalized)) return normalized;
    return fallback;
  };

  // A/B variant overrides
  const ctaText = sanitizeCtaText(getConfig('cta_text', 'View Plans & Upgrade'), 'View Plans & Upgrade');
  const ctaColor = sanitizeCtaColor(getConfig('cta_color', requiredPlanData.color), requiredPlanData.color);
  const ctaForeground = getReadableTextColor(ctaColor, {
    light: colors.primaryText,
    dark: colors.text,
  });
  const modalTitle = getConfig('title', 'Upgrade to Unlock');
  const modalSubtitle = getConfig('subtitle', '');
  const badgeLabel = getConfig('badge_text', 'Recommended');

  return (
    <Modal transparent visible={visible} animationType="none" onRequestClose={close}>
      <Animated.View style={[styles.overlay, { opacity: fadeAnim }]}>
        <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={close} accessibilityLabel="close" />
        <Animated.View style={[
          styles.container,
          { backgroundColor: colors.card, transform: [{ translateY: slideAnim }] },
        ]}>
          <ScrollView bounces={false} showsVerticalScrollIndicator={false}>
            {/* Close button */}
            <TouchableOpacity
              style={[styles.closeBtn, { backgroundColor: colors.bgSoft }]}
              onPress={close}
              data-testid="upgrade-modal-close-btn" testID="upgrade-modal-close-btn"
            >
              <Ionicons name="close" size={20} color={colors.textMuted} />
            </TouchableOpacity>

            {/* Lock icon header */}
            <View style={[styles.lockCircle, { backgroundColor: (globalThis as any).__alphaColor(requiredPlanData.color, '18') }]}>
              <Ionicons name="lock-closed" size={28} color={requiredPlanData.color} />
            </View>

            <Text style={[styles.title, { color: colors.text }]} data-testid="upgrade-modal-title" testID="upgrade-modal-title">
              {modalTitle}
            </Text>
            <Text style={[styles.subtitle, { color: colors.textMuted }]} data-testid="upgrade-modal-message" testID="upgrade-modal-message">
              {modalSubtitle || payload.message || `This feature requires a ${requiredPlanData.name} plan or higher.`}
            </Text>

            {/* Plan comparison */}
            <View style={styles.plansRow}>
              {/* Current plan (dimmed) */}
              <View style={[styles.planCard, styles.planCardCurrent, { borderColor: colors.border, backgroundColor: colors.bgSoft }]}>
                <Text style={[styles.planLabel, { color: colors.textMuted }]}>Current</Text>
                <View style={[styles.planIconCircle, { backgroundColor: `${colors.textMuted}18` }]}>
                  <Ionicons name="person-outline" size={18} color={colors.textMuted} />
                </View>
                <Text style={[styles.planName, { color: colors.textMuted }]}>
                  {(currentPlan || 'free').charAt(0).toUpperCase() + (currentPlan || 'free').slice(1)}
                </Text>
              </View>

              {/* Arrow */}
              <View style={styles.arrowContainer}>
                <Ionicons name="arrow-forward" size={20} color={requiredPlanData.color} />
              </View>

              {/* Required plan (highlighted) */}
              <View style={[
                styles.planCard, styles.planCardRequired,
                { borderColor: requiredPlanData.color, backgroundColor: (globalThis as any).__alphaColor(requiredPlanData.color, '0A') },
              ]}>
                <View style={[styles.recommendBadge, { backgroundColor: requiredPlanData.color }]}>
                  <Text style={styles.recommendText}>{badgeLabel}</Text>
                </View>
                <View style={[styles.planIconCircle, { backgroundColor: (globalThis as any).__alphaColor(requiredPlanData.color, '18') }]}>
                  <Ionicons name={requiredPlanData.icon} size={18} color={requiredPlanData.color} />
                </View>
                <Text style={[styles.planName, { color: colors.text }]}>
                  {requiredPlanData.name}
                </Text>
                <Text style={[styles.planPrice, { color: requiredPlanData.color }]}>
                  {requiredPlanData.price}<Text style={styles.planPeriod}>/mo</Text>
                </Text>
              </View>
            </View>

            {/* Feature list for recommended plan */}
            <View style={[styles.featuresBox, { backgroundColor: colors.bgSoft, borderColor: colors.border }]}>
              <Text style={[styles.featuresTitle, { color: colors.text }]}>
                What you get with {requiredPlanData.name}
              </Text>
              {requiredPlanData.features.map((f, i) => (
                <View key={i} style={styles.featureRow}>
                  <Ionicons name="checkmark-circle" size={16} color={requiredPlanData.color} />
                  <Text style={[styles.featureText, { color: colors.textSec }]}>{f}</Text>
                </View>
              ))}
            </View>

            {/* CTA buttons */}
            <TouchableOpacity
              style={[styles.upgradeBtn, { backgroundColor: ctaColor }]}
              onPress={handleUpgrade}
              activeOpacity={0.85}
              data-testid="upgrade-modal-upgrade-btn" testID="upgrade-modal-upgrade-btn"
            >
              <Ionicons name="rocket" size={18} color={ctaForeground} />
              <Text style={[styles.upgradeBtnText, { color: ctaForeground }]}>{ctaText}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.laterBtn}
              onPress={close}
              activeOpacity={0.7}
              data-testid="upgrade-modal-later-btn" testID="upgrade-modal-later-btn"
            >
              <Text style={[styles.laterBtnText, { color: colors.textMuted }]}>Maybe Later</Text>
            </TouchableOpacity>
          </ScrollView>
        </Animated.View>
      </Animated.View>
    </Modal>
  );
}

const { width: SCREEN_W } = Dimensions.get('window');
const MODAL_W = Math.min(SCREEN_W - 40, 420);

/* i18n-probe t('i18n.auto.probe') */
