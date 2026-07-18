import React from 'react';
import { View, Text } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from '../hooks/useTranslation';
import { useTheme } from '../context/ThemeContext';

// Graceful native placeholder for surfaces that are intentionally web-only
// (operations console, executive dashboard, WebGL game). Prevents the native
// runtime from mounting DOM/recharts/three-dependent component trees.
export const WebOnlyScreen = ({
  featureNameKey,
  featureNameFallback,
}: {
  featureNameKey: string;
  featureNameFallback: string;
}) => {
  const { tx } = useTranslation();
  const { colors } = useTheme();
  return (
    <View
      style={{
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: colors.background,
        padding: 32,
        gap: 12,
      }}
      testID="web-only-screen"
    >
      <Ionicons name="desktop-outline" size={56} color={colors.textMuted} />
      <Text
        style={{ color: colors.text, fontSize: 20, fontWeight: '700', textAlign: 'center', marginTop: 8 }}
        testID="web-only-feature-name"
      >
        {tx(featureNameKey, featureNameFallback)}
      </Text>
      <Text style={{ color: colors.textSec, fontSize: 15, textAlign: 'center' }}>
        {tx('webOnly.availableOnWeb', 'This feature is available on the web app.')}
      </Text>
      <Text style={{ color: colors.primary, fontSize: 15, fontWeight: '600' }}>realaicoach.app</Text>
    </View>
  );
};
