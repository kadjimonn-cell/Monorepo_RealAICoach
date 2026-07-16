/**
 * UIEM Safe Fallback — V2-themed fallback card shown when validation fails.
 * Never shows blank screen, broken UI, or infinite loader.
 */
import React from 'react';
import { View, Text} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface UIEMFallbackProps {
  componentName: string;
  layer: string;
  message?: string;
  showSkeleton?: boolean;
}

export function UIEMFallback({ componentName, layer, message, showSkeleton }: UIEMFallbackProps) {
  const { colors, _darkMode } = useTheme();

  if (showSkeleton) {
    return (
      <View
        style={{
          backgroundColor: colors.card,
          borderRadius: 12,
          padding: 16,
          margin: 4,
          minHeight: 80,
        }}
        data-testid="uiem-skeleton-fallback"
        testID="uiem-skeleton-fallback"
      >
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center', marginBottom: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: colors.skeleton }} />
          <View style={{ flex: 1, gap: 6 }}>
            <View style={{ width: '60%', height: 10, borderRadius: 5, backgroundColor: colors.skeleton }} />
            <View style={{ width: '40%', height: 8, borderRadius: 4, backgroundColor: colors.skeleton }} />
          </View>
        </View>
        <View style={{ width: '100%', height: 8, borderRadius: 4, backgroundColor: colors.skeleton, marginBottom: 6 }} />
        <View style={{ width: '80%', height: 8, borderRadius: 4, backgroundColor: colors.skeleton }} />
      </View>
    );
  }

  return (
    <View
      style={{
        backgroundColor: colors.card,
        borderWidth: 1,
        borderColor: colors.border,
        borderRadius: 12,
        padding: 16,
        margin: 4,
        alignItems: 'center',
        gap: 8,
      }}
      data-testid="uiem-fallback-card"
      testID="uiem-fallback-card"
    >
      <View style={{
        width: 36, height: 36, borderRadius: 18,
        backgroundColor: colors.card,
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Ionicons name="shield-outline" size={18} color={colors.warningText} />
      </View>
      <Text style={{ color: colors.text, fontSize: 13, fontWeight: '700', textAlign: 'center' }}>
        Component temporarily unavailable
      </Text>
      <Text style={{ color: colors.textMuted, fontSize: 10, textAlign: 'center' }}>
        {message || `${componentName} is being validated`}
      </Text>
      <View style={{
        flexDirection: 'row', alignItems: 'center', gap: 4,
        backgroundColor: colors.card,
        paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6,
      }}>
        <Ionicons name="lock-closed" size={9} color={colors.textMuted} />
        <Text style={{ color: colors.textMuted, fontSize: 8, fontWeight: '600' }}>
          UIEM Layer: {layer}
        </Text>
      </View>
    </View>
  );
}
