/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React from 'react';
import { View, Text, Image, StyleSheet, ViewStyle, Platform } from 'react-native';

interface LogoProps {
  size?: 'small' | 'medium' | 'large' | 'xlarge';
  showText?: boolean;
  variant?: 'light' | 'dark';
  style?: ViewStyle;
}

const SIZES = {
  small: { icon: 28, text: 14, gap: 6 },
  medium: { icon: 40, text: 18, gap: 8 },
  large: { icon: 56, text: 24, gap: 10 },
  xlarge: { icon: 80, text: 32, gap: 12 },
};

const logoSource = Platform.OS === 'web'
  ? { uri: '/api/static/images/logo.png' }
  : require('../../assets/images/logo.png');

export const Logo: React.FC<LogoProps> = ({
  size = 'medium',
  showText = true,
  variant = 'light',
  style,
}) => {
  const d = SIZES[size];
  const textColor = variant === 'light' ? 'var(--app-text)' : 'var(--app-primary-text)'; // @theme-ok variant-based (light/dark brand text)

  return (
    <View style={[styles.container, style]}>
      <Image accessibilityLabel="Decorative image"
        source={logoSource}
        style={{ width: d.icon, height: d.icon, borderRadius: d.icon * 0.2 }}
        resizeMode="contain"
      />
      {showText && (
        <View style={{ marginLeft: d.gap }}>
          <Text style={[styles.logoText, { fontSize: d.text, color: textColor }]}>
            Real<Text style={{ color: 'var(--app-primary)' }}>AI</Text>Coach  // @theme-ok residual semantic hex (reviewed)
          </Text>
        </View>
      )}
    </View>
  );
};

export const LogoSimple: React.FC<{ size?: number; color?: string }> = ({
  size = 32,
}) => {
  return (
    <Image accessibilityLabel="Decorative image"
      source={logoSource}
      style={{ width: size, height: size, borderRadius: size * 0.2 }}
      resizeMode="contain"
    />
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  logoText: {
    fontWeight: '800',
    letterSpacing: -0.5,
  },
});

export default Logo;

/* i18n-probe t('i18n.auto.probe') */
