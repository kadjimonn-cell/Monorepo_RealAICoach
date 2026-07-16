import React, { Suspense } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

const LazyLogin = React.lazy(() => import('../src/components/pages/LoginInner'));

function LoginFallback() {
  const { colors } = useTheme();
  return (
    <View
      style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg }}
      data-testid="login-route-fallback" testID="login-route-fallback"
    >
      <ActivityIndicator size="large" color={colors.primary} />
    </View>
  );
}

export default function CompactLoginScreen() {
  const { t } = useTranslation();
  t('i18n.route.login.probe');
  const params = useLocalSearchParams<{ compact?: string }>();
  const forceCompactMode = params.compact === '1';

  return (
    <Suspense fallback={<LoginFallback />}>
      <LazyLogin forceCompactMode={forceCompactMode} />
    </Suspense>
  );
}