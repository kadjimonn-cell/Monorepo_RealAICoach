import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';

interface AITransparencyBannerProps {
  title?: string;
  subtitle?: string;
  testId?: string;
}

export default function AITransparencyBanner({
  title = 'AI-generated guidance',
  subtitle = 'This assistant uses AI and may be inaccurate. For critical decisions, consult qualified professionals.',
  testId = 'ai-transparency-banner',
}: AITransparencyBannerProps) {
  const { colors, darkMode } = useTheme();

  return (
    <View
      style={[styles.container, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}
      data-testid={testId} testID={testId}
      accessibilityRole="summary"
    >
      <View style={[styles.iconWrap, { backgroundColor: colors.primarySoft }]}>
        <Ionicons name="sparkles" size={18} color={colors.primary} />
      </View>
      <View style={styles.textWrap}>
        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
        <Text style={[styles.subtitle, { color: darkMode ? colors.textSec : colors.textMuted }]}>{subtitle}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    gap: 12,
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    marginBottom: 16,
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textWrap: {
    flex: 1,
    gap: 4,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 12,
    lineHeight: 18,
  },
});

/* i18n-probe t('i18n.auto.probe') */
