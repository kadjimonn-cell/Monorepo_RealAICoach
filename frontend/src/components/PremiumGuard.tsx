import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '../context/ThemeContext';
import { useSubscription } from '../context/SubscriptionContext';
import { FontAwesome5 } from '@expo/vector-icons';

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

interface PremiumGuardProps {
  children: React.ReactNode;
  featureName: string;
  requiredPlan?: 'basic' | 'premium';
}

export default function PremiumGuard({ children, featureName, requiredPlan = 'premium' }: PremiumGuardProps) {
  const { colors: theme } = useTheme();
  const { canAccess, plan } = useSubscription();
  const router = useRouter();

  if (canAccess(requiredPlan)) {
    return <>{children}</>;
  }

  const isBasicRequired = requiredPlan === 'basic';
  const accentColor = isBasicRequired ? theme.primary : theme.warning;
  const upgradeTextColor = getReadableTextColor(accentColor, {
    light: theme.primaryText,
    dark: theme.text,
  });
  const planLabel = isBasicRequired ? 'Basic' : 'Premium';

  return (
    <View style={[styles.container, { backgroundColor: theme.bg }]} data-testid={`premium-guard-${featureName.toLowerCase().replace(/\s+/g, '-')}`} testID={`premium-guard-${featureName.toLowerCase().replace(/\s+/g, '-')}`}>
      <View style={[styles.iconContainer, { backgroundColor: (globalThis as any).__alphaColor(accentColor, '18') }]}>
        <FontAwesome5 name={isBasicRequired ? 'star' : 'crown'} size={40} color={accentColor} />
      </View>
      <Text style={[styles.title, { color: theme.text }]} data-testid="premium-guard-title" testID="premium-guard-title">
        {planLabel} Feature
      </Text>
      <Text style={[styles.subtitle, { color: theme.textSec }]} data-testid="premium-guard-subtitle" testID="premium-guard-subtitle">
        {featureName} requires a {planLabel} plan or higher. Upgrade to unlock this and all {isBasicRequired ? 'standard' : 'advanced AI'} tools.
      </Text>
      <View style={styles.currentPlanRow}>
        <Text style={{ color: theme.textMuted, fontSize: 13 }}>Your current plan: </Text>
        <View style={{ backgroundColor: theme.bgSoft, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 }}>
          <Text style={{ color: theme.text, fontWeight: '700', fontSize: 13 }}>{plan.charAt(0).toUpperCase() + plan.slice(1)}</Text>
        </View>
      </View>
      <TouchableOpacity
        style={[styles.upgradeBtn, { backgroundColor: accentColor }]}
        onPress={() => router.push('/subscription/plans')}
        data-testid="premium-guard-upgrade" testID="premium-guard-upgrade"
        accessibilityRole="button"
      >
        <Text style={[styles.upgradeText, { color: upgradeTextColor }]}>Upgrade to {planLabel}</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={styles.backBtn}
        onPress={() => router.back()}
        data-testid="premium-guard-back" testID="premium-guard-back"
        accessibilityRole="button"
      >
        <Text style={[styles.backText, { color: theme.textMuted }]}>Maybe Later</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  iconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '800',
    marginBottom: 12,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 16,
    textAlign: 'center',
    marginBottom: 20,
    lineHeight: 24,
  },
  currentPlanRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 28,
  },
  upgradeBtn: {
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 16,
    width: '100%',
    alignItems: 'center',
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 4px 8px rgba(0,0,0,0.15)' }
      : { shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.15, shadowRadius: 8, elevation: 4 }),
  },
  upgradeText: {
    fontSize: 16,
    fontWeight: '700',
  },
  backBtn: {
    marginTop: 20,
    padding: 10,
  },
  backText: {
    fontSize: 14,
  },
});

/* i18n-probe t('i18n.auto.probe') */
