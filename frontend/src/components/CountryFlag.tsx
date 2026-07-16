import React, { useState } from 'react';
import { Image, Text, StyleProp, ViewStyle } from 'react-native';

const emojiToIso = (emoji?: string): string => {
  if (!emoji) return '';
  const letters = Array.from(emoji)
    .map((c) => c.codePointAt(0) || 0)
    .filter((cp) => cp >= 0x1f1e6 && cp <= 0x1f1ff)
    .map((cp) => String.fromCharCode(cp - 0x1f1e6 + 65));
  return letters.length === 2 ? letters.join('') : '';
};

interface CountryFlagProps {
  code?: string;
  emoji?: string;
  size?: number;
  style?: StyleProp<ViewStyle>;
}

export const CountryFlag = ({ code, emoji, size = 16, style }: CountryFlagProps) => {
  const [failed, setFailed] = useState(false);
  const iso = (code && /^[A-Za-z]{2}$/.test(code.trim()) ? code.trim() : emojiToIso(emoji)).toLowerCase();

  if (!iso || failed) {
    return (
      <Text
        data-testid="country-flag-fallback"
        style={[{ fontSize: size, lineHeight: size + 2 }, style as any]}
      >
        {emoji || '🌍'}
      </Text>
    );
  }

  return (
    <Image
      data-testid={`country-flag-${iso}`}
      testID={`country-flag-${iso}`}
      source={{ uri: `https://flagcdn.com/w80/${iso}.png` }}
      onError={() => setFailed(true)}
      style={[{ width: Math.round((size * 4) / 3), height: size, borderRadius: 2 }, style]}
      resizeMode="cover"
      accessibilityLabel={`${iso.toUpperCase()} flag`}
    />
  );
};

export default CountryFlag;
