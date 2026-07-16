import React, { useEffect, useRef, useState } from 'react';
import { View, Text, Image, Animated, Easing, Pressable, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { NOVA_PORTRAIT_URL } from '../../constants/novaPersona';
import { useTheme } from '../../context/ThemeContext';

type AvatarAnimationPreset = 'none' | 'subtle' | 'interactive';

type AvatarBadgeProps = {
  size?: number;
  ringColor: string;
  surfaceColor: string;
  showOnlineDot?: boolean;
  onlineDotColor?: string;
  animationPreset?: AvatarAnimationPreset;
  wrapTestId: string;
  imageTestId: string;
  dotTestId?: string;
};

export const NovaAvatarBadge = ({
  size = 44,
  ringColor,
  surfaceColor,
  showOnlineDot = false,
  onlineDotColor,
  animationPreset = 'none',
  wrapTestId,
  imageTestId,
  dotTestId,
}: AvatarBadgeProps) => {
  const { colors } = useTheme();
  const pulse = useRef(new Animated.Value(1)).current;
  const hoverLift = useRef(new Animated.Value(0)).current;
  const [imageLoadFailed, setImageLoadFailed] = useState(false);

  useEffect(() => {
    const pulseDisabledForE2E = Boolean((globalThis as any)?.__E2E_DISABLE_NOVA_PULSE__);
    const shouldPulse = animationPreset === 'subtle' || animationPreset === 'interactive';
    if (!shouldPulse || pulseDisabledForE2E) {
      pulse.setValue(1);
      return;
    }

    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1.02,
          duration: 1800,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1800,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ]),
    );

    pulseLoop.start();
    return () => {
      pulseLoop.stop();
      pulse.stopAnimation();
      pulse.setValue(1);
    };
  }, [animationPreset, pulse]);

  const handleHoverIn = () => {
    if (animationPreset !== 'interactive' || Platform.OS !== 'web') return;
    Animated.timing(hoverLift, {
      toValue: -2,
      duration: 180,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    }).start();
  };

  const handleHoverOut = () => {
    if (animationPreset !== 'interactive' || Platform.OS !== 'web') return;
    Animated.timing(hoverLift, {
      toValue: 0,
      duration: 180,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    }).start();
  };

  const innerSize = Math.max(size - 2, 2);
  const fallbackIconSize = Math.max(12, Math.round(innerSize * 0.44));
  const shouldRenderImage = Boolean(NOVA_PORTRAIT_URL) && !imageLoadFailed;
  return (
    <Pressable accessibilityLabel="Nova identity badge action button 1"
      onHoverIn={handleHoverIn}
      onHoverOut={handleHoverOut}
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
      }}
      data-testid={wrapTestId}
      testID={wrapTestId}
    >
      <Animated.View
        data-testid={`${wrapTestId}-animated`}
        testID={`${wrapTestId}-animated`}
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: 1.5,
          borderColor: ringColor,
          backgroundColor: surfaceColor,
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          transform: [{ scale: pulse }, { translateY: hoverLift }],
        }}
      >
        {shouldRenderImage ? (
          <Image accessibilityLabel="Decorative image"
            source={{ uri: NOVA_PORTRAIT_URL }}
            style={{ width: innerSize, height: innerSize, borderRadius: innerSize / 2 }}
            resizeMode="cover"
            data-testid={imageTestId}
            testID={imageTestId}
            onError={() => setImageLoadFailed(true)}
            onLoad={() => setImageLoadFailed(false)}
          />
        ) : (
          <View
            style={{
              width: innerSize,
              height: innerSize,
              borderRadius: innerSize / 2,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: (globalThis as any).__alphaColor(colors.primary, '14'),
            }}
            data-testid={`${imageTestId}-fallback`}
            testID={`${imageTestId}-fallback`}
          >
            <Ionicons name="sparkles" size={fallbackIconSize} color={colors.primary} />
          </View>
        )}
        {showOnlineDot ? (
          <View
            style={{
              position: 'absolute',
              right: Math.max(2, Math.round(size * 0.06)),
              bottom: Math.max(2, Math.round(size * 0.06)),
              width: Math.max(8, Math.round(size * 0.24)),
              height: Math.max(8, Math.round(size * 0.24)),
              borderRadius: 99,
              backgroundColor: onlineDotColor || colors.success,
              borderWidth: 1,
              borderColor: surfaceColor,
            }}
            data-testid={dotTestId || `${wrapTestId}-online-dot`}
            testID={dotTestId || `${wrapTestId}-online-dot`}
          />
        ) : null}
      </Animated.View>
    </Pressable>
  );
};

type CalloutProps = {
  kicker: string;
  introText: string;
  borderColor: string;
  backgroundColor: string;
  kickerColor: string;
  textColor: string;
  avatarRingColor: string;
  avatarSurfaceColor: string;
  avatarSize?: number;
  avatarAnimationPreset?: AvatarAnimationPreset;
  prefix: string;
  introTestId?: string;
  centered?: boolean;
};

export const NovaIdentityCallout = ({
  kicker,
  introText,
  borderColor,
  backgroundColor,
  kickerColor,
  textColor,
  avatarRingColor,
  avatarSurfaceColor,
  avatarSize = 44,
  avatarAnimationPreset = 'none',
  prefix,
  introTestId,
  centered = false,
}: CalloutProps) => {
  return (
    <View
      style={{
        borderRadius: 14,
        borderWidth: 1,
        borderColor,
        backgroundColor,
        paddingHorizontal: 12,
        paddingVertical: 10,
        flexDirection: 'row',
        gap: 10,
        alignItems: 'center',
        justifyContent: centered ? 'center' : undefined,
        width: '100%',
      }}
      data-testid={`${prefix}-card`}
      testID={`${prefix}-card`}
    >
      <NovaAvatarBadge
        size={avatarSize}
        ringColor={avatarRingColor}
        surfaceColor={avatarSurfaceColor}
        animationPreset={avatarAnimationPreset}
        wrapTestId={`${prefix}-avatar-wrap`}
        imageTestId={`${prefix}-avatar-image`}
      />
      <View style={{ flex: 1, alignItems: centered ? 'center' : undefined }}>
        <Text
          style={{
            color: kickerColor,
            fontSize: 10,
            fontWeight: '800',
            letterSpacing: 0.7,
            textTransform: 'uppercase',
            marginBottom: 2,
            textAlign: centered ? 'center' : undefined,
          }}
          data-testid={`${prefix}-kicker`}
          testID={`${prefix}-kicker`}
        >
          {kicker}
        </Text>
        <Text
          style={{ color: textColor, fontSize: 12, lineHeight: 18, fontWeight: '700', textAlign: centered ? 'center' : undefined }}
          data-testid={introTestId || `${prefix}-intro-text`}
          testID={introTestId || `${prefix}-intro-text`}
        >
          {introText}
        </Text>
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
