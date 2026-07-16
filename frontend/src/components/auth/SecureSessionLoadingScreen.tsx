import React from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';

export function SecureSessionLoadingScreen({
  title,
  message,
}: {
  title?: string;
  message?: string;
}) {
  const { t } = useLanguage();
  const { colors } = useTheme();
  const resolvedTitle = title ?? t('authGate.checkingSession');
  const resolvedMessage = message ?? t('authGate.verifyAccessWait');

  return (
    <View
      style={{
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 24,
        backgroundColor: colors.bg,
      }}
      data-testid="secure-session-loading-screen"
      testID="secure-session-loading-screen"
    >
      <View
        style={{
          width: '100%',
          maxWidth: 420,
          borderRadius: 24,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.card,
          paddingHorizontal: 24,
          paddingVertical: 28,
          alignItems: 'center',
        }}
      >
        <ActivityIndicator size="small" color={colors.primary} />
        <Text
          style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginTop: 14, textAlign: 'center' }}
          data-testid="secure-session-loading-title"
          testID="secure-session-loading-title"
        >
          {resolvedTitle}
        </Text>
        <Text
          style={{ color: colors.textMuted, fontSize: 13, lineHeight: 20, marginTop: 8, textAlign: 'center' }}
          data-testid="secure-session-loading-message"
          testID="secure-session-loading-message"
        >
          {resolvedMessage}
        </Text>
      </View>
    </View>
  );
}