import React from 'react';
import { View, Text } from 'react-native';
import { useTheme } from '../../context/ThemeContext';

interface BlogSectionTitleProps {
  title: string;
  subtitle?: string;
  testId: string;
}

export function BlogSectionTitle({ title, subtitle, testId }: BlogSectionTitleProps) {
  const { colors } = useTheme();

  return (
    <View style={{ marginBottom: 14, gap: 4 }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.text, fontSize: 24, fontWeight: '800', letterSpacing: -0.4 }}>{title}</Text>
      {subtitle ? <Text style={{ color: colors.textSecondary, fontSize: 14 }}>{subtitle}</Text> : null}
    </View>
  );
}
