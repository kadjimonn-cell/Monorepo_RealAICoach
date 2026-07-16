import React, { useEffect, useRef } from 'react';
import { View, Text, Animated, Platform } from 'react-native';
import { useTheme } from '../context/ThemeContext';
import { withAlpha } from '../utils/colorAlpha';
import { IDENTITY_LAYOUT } from '../constants/identityLayout';

interface SubscriptionBadgeProps {
  plan: 'free' | 'basic' | 'premium' | string;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  isAdmin?: boolean;
  compact?: boolean;
}

const BADGE_SIZE_MAP = {
  sm: { badge: 20, font: 10, icon: 11, pad: 5 },
  md: { badge: 26, font: 11, icon: 13, pad: 8 },
  lg: { badge: 32, font: 13, icon: 16, pad: 10 },
};

function OwnerBadge({ size = 'md', compact = false }: { size: 'sm' | 'md' | 'lg'; compact?: boolean }) {
  const {darkMode, _colors} = useTheme();
  const s = BADGE_SIZE_MAP[size];
  const shimmer = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (Platform.OS === 'web') {
      Animated.loop(
        Animated.sequence([
          Animated.timing(shimmer, { toValue: 1, duration: 2000, useNativeDriver: false }),
          Animated.timing(shimmer, { toValue: 0, duration: 2000, useNativeDriver: false }),
        ])
      ).start();
    }
  }, [shimmer]);

  const borderColor = _colors.primary;

  const glowOpacity = shimmer.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0.4, 0.9, 0.4],
  });

  return (
    <View data-testid="subscription-badge-owner" testID="subscription-badge-owner">
      {/* Outer glow layer */}
      {Platform.OS === 'web' && (
        <Animated.View
          style={{
            position: 'absolute',
            top: -2,
            left: -2,
            right: -2,
            bottom: -2,
            borderRadius: s.badge + 2,
            opacity: glowOpacity,
            ...(Platform.OS === 'web' ? {
              boxShadow: `0 0 10px 2px ${withAlpha(_colors.primary, '42')}, 0 0 20px 4px ${withAlpha(_colors.primary, '24')}`,
            } as any : {}),
          }}
        />
      )}
      {/* Main badge */}
      <Animated.View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 4,
          minWidth: compact ? IDENTITY_LAYOUT.ownerBadge.compactMinWidth : undefined,
          justifyContent: 'center',
          backgroundColor: withAlpha(_colors.primary, darkMode ? IDENTITY_LAYOUT.ownerBadge.alphaDark : IDENTITY_LAYOUT.ownerBadge.alphaLight),
          borderWidth: 1.5,
          borderColor: withAlpha(borderColor, IDENTITY_LAYOUT.ownerBadge.borderAlpha),
          borderRadius: s.badge,
          paddingHorizontal: compact ? Math.max(6, s.pad) : s.pad + 2,
          paddingVertical: compact ? Math.max(2, Math.floor(s.pad / 2)) : (s.pad / 2 + 1),
        }}
        data-testid={compact ? 'subscription-badge-owner-compact' : 'subscription-badge-owner-full'}
        testID={compact ? 'subscription-badge-owner-compact' : 'subscription-badge-owner-full'}
      >
        <Text style={{ fontSize: s.icon + 1, color: _colors.text }}>{'\u{1F451}'}</Text>
        <Text
          style={{
            fontSize: compact ? (s.font + 1) : s.font,
            fontWeight: '900',
            color: _colors.text,
            letterSpacing: compact ? 0.4 : 0.8,
            textTransform: 'uppercase',
          }}
        >
          {compact ? IDENTITY_LAYOUT.ownerBadge.compactText : IDENTITY_LAYOUT.ownerBadge.fullText}
        </Text>
      </Animated.View>
    </View>
  );
}

export default function SubscriptionBadge({ plan, size = 'md', showLabel = true, isAdmin = false, compact = false }: SubscriptionBadgeProps) {
  const { _colors } = useTheme();
  const BADGE_CONFIG = {
    free: {
      label: 'Free',
      bg: withAlpha(_colors.primary, '10'),
      border: withAlpha(_colors.primary, '28'),
      text: _colors.text,
      glow: false,
    },
    basic: {
      label: 'Basic',
      bg: withAlpha(_colors.primary, IDENTITY_LAYOUT.ownerBadge.alphaLight),
      border: withAlpha(_colors.primary, '45'),
      text: _colors.text,
      glow: true,
    },
    premium: {
      label: 'Premium',
      bg: withAlpha(_colors.success, IDENTITY_LAYOUT.ownerBadge.alphaLight),
      border: withAlpha(_colors.success, '45'),
      text: _colors.text,
      glow: true,
    },
  };
  const config = BADGE_CONFIG[plan as keyof typeof BADGE_CONFIG] || BADGE_CONFIG.free;
  const s = BADGE_SIZE_MAP[size];
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (!isAdmin && config.glow && Platform.OS === 'web') {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1.08, duration: 1200, useNativeDriver: Platform.OS !== 'web' }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 1200, useNativeDriver: Platform.OS !== 'web' }),
        ])
      ).start();
    }
  }, [isAdmin, config.glow, pulseAnim]);

  if (isAdmin) {
    return <OwnerBadge size={size} compact={compact} />;
  }

  const isPremium = plan === 'premium';
  const isBasic = plan === 'basic';

  return (
    <Animated.View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        backgroundColor: config.bg,
        borderWidth: 1,
        borderColor: config.border,
        borderRadius: s.badge,
        paddingHorizontal: s.pad,
        paddingVertical: s.pad / 2,
        transform: [{ scale: config.glow ? pulseAnim : 1 }],
      }}
      data-testid={`subscription-badge-${plan}`} testID={`subscription-badge-${plan}`}
    >
      <Text style={{ fontSize: s.icon }}>
        {isPremium ? '\u2B50' : isBasic ? '\u2728' : '\u26AA'}
      </Text>
      {showLabel && (
        <Text
          style={{
            fontSize: s.font,
            fontWeight: '800',
            color: config.text,
            letterSpacing: 0.5,
            textTransform: 'uppercase',
          }}
        >
          {config.label}
        </Text>
      )}
    </Animated.View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
