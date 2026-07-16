import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useLiveQuery } from '../hooks/useLiveQuery';

const GLOBAL_RENEWAL_FETCH_MARKERS = new Set<string>();
const RENEWAL_GUARDRAIL_STABILITY_MODE = true;

// ── Inline contrast color helper (avoids Metro resolution issues) ──
type Rgb = { r: number; g: number; b: number };

const CSS_VAR_FALLBACKS: Record<string, string> = {
  '--app-primary': '#0F766E', // @theme-ok css-var runtime fallback
  '--app-primary-text': '#FFFFFF', // @theme-ok css-var runtime fallback
  '--app-text': '#0F172A', // @theme-ok css-var runtime fallback
  '--app-warning': '#D97706', // @theme-ok css-var runtime fallback
  '--app-success': '#16A34A', // @theme-ok css-var runtime fallback
  '--app-error': '#DC2626', // @theme-ok css-var runtime fallback
  '--app-info': '#0284C7', // @theme-ok css-var runtime fallback
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

interface BannerData {
  show_banner: boolean;
  banner_type?: string;
  title?: string;
  message?: string;
  cta_text?: string;
  cta_url?: string;
  urgency?: string;
  days_left?: number;
}

export default function RenewalBanner() {
  const stabilityMode = RENEWAL_GUARDRAIL_STABILITY_MODE;

  const { user } = useAuth();
  const { colors } = useTheme();
  const router = useRouter();
  const [banner, setBanner] = useState<BannerData | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const fadeAnim = useState(() => new Animated.Value(0))[0];
  const renewalFetchInFlightRef = React.useRef(false);
  const renewalCooldownUntilRef = React.useRef(0);
  const renewalFetchedForUserRef = React.useRef<string>('');

  const hasRenewalFetchMarker = (userId: string) => {
    if (!userId || Platform.OS !== 'web' || typeof window === 'undefined') return false;
    try {
      return window.sessionStorage.getItem(`renewal:banner:fetched:${userId}`) === '1';
    } catch {
      return false;
    }
  };

  const setRenewalFetchMarker = (userId: string) => {
    if (!userId || Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      window.sessionStorage.setItem(`renewal:banner:fetched:${userId}`, '1');
    } catch {
      // no-op
    }
  };

  useEffect(() => {
    if (stabilityMode) return;
    if (!user) return;
    const path = String((globalThis as any)?.window?.location?.pathname || '/');
    const allowBannerOnRoute = path === '/dashboard'
      || path === '/home'
      || path.startsWith('/dashboard/')
      || path.startsWith('/home/')
      || path === '/subscription/plans';
    if (!allowBannerOnRoute) return;

    const now = Date.now();
    const currentUserId = String((user as any)?.user_id || '');
    if (GLOBAL_RENEWAL_FETCH_MARKERS.has(currentUserId)) return;
    if (hasRenewalFetchMarker(currentUserId)) return;
    if (renewalFetchedForUserRef.current === currentUserId) return;
    if (renewalFetchInFlightRef.current || now < renewalCooldownUntilRef.current) return;

    renewalFetchInFlightRef.current = true;
    renewalFetchedForUserRef.current = currentUserId;
    setRenewalFetchMarker(currentUserId);
    GLOBAL_RENEWAL_FETCH_MARKERS.add(currentUserId);
    api.get('/subscriptions/renewal-banner')
      .then(res => {
        if (res.data?.show_banner) {
          setBanner(res.data);
          Animated.timing(fadeAnim, { toValue: 1, duration: 400, useNativeDriver: Platform.OS !== 'web' }).start();
        }
      })
      .catch(() => {
        renewalCooldownUntilRef.current = Date.now() + 120000;
      })
      .finally(() => {
        renewalFetchInFlightRef.current = false;
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, stabilityMode]);

  if (stabilityMode) {
    return null;
  }

  if (!banner || !banner.show_banner || dismissed) return null;

  const urgencyConfig: Record<string, { bg: string; border: string; icon: string; iconColor: string }> = {
    critical: { bg: colors.errorSoft, border: colors.errorSoft, icon: 'alert-circle', iconColor: colors.error },
    high: { bg: colors.warningSoft, border: colors.warningSoft, icon: 'warning', iconColor: colors.warningText },
    medium: { bg: colors.primarySoft, border: colors.primarySoft, icon: 'information-circle', iconColor: colors.primary },
    low: { bg: colors.successSoft, border: colors.successSoft, icon: 'arrow-up-circle', iconColor: colors.successText },
  };

  const cfg = urgencyConfig[banner.urgency || 'low'] || urgencyConfig.low;
  const ctaTextColor = getReadableTextColor(cfg.iconColor, {
    light: colors.primaryText,
    dark: colors.text,
  });

  return (
    <Animated.View
      style={[
        styles.container,
        { backgroundColor: cfg.bg, borderColor: cfg.border, opacity: fadeAnim },
      ]}
      data-testid="renewal-banner" testID="renewal-banner"
    >
      <View style={styles.iconWrap}>
        <Ionicons name={cfg.icon as any} size={22} color={cfg.iconColor} />
      </View>
      <View style={styles.content}>
        <Text style={[styles.title, { color: colors.text }]} data-testid="renewal-banner-title" testID="renewal-banner-title">{banner.title}</Text>
        <Text style={[styles.message, { color: colors.textSecondary }]} numberOfLines={2}>{banner.message}</Text>
      </View>
      <View style={styles.actions}>
        {banner.cta_text && (
          <TouchableOpacity
            style={[styles.ctaBtn, { backgroundColor: cfg.iconColor }]}
            onPress={() => router.push(banner.cta_url || '/subscription/plans')}
            data-testid="renewal-banner-cta" testID="renewal-banner-cta"
          >
            <Text style={[styles.ctaText, { color: ctaTextColor }]}>{banner.cta_text}</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity onPress={() => setDismissed(true)} style={styles.dismissBtn} data-testid="renewal-banner-dismiss" testID="renewal-banner-dismiss">
          <Ionicons name="close" size={18} color={colors.textMuted} />
        </TouchableOpacity>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    borderWidth: 1,
    marginHorizontal: 16,
    marginTop: 8,
  },
  iconWrap: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  content: { flex: 1, gap: 2 },
  title: { fontSize: 14, fontWeight: '700' },
  message: { fontSize: 12, lineHeight: 16 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  ctaBtn: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  ctaText: { fontSize: 12, fontWeight: '700' },
  dismissBtn: { padding: 4 },
});

/* i18n-probe t('i18n.auto.probe') */
