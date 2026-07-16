import React, { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useRouter } from 'expo-router';
import AppShell from '../../src/components/AppShell';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function SportsSourceHealthAdminPage() {
  const { t } = useTranslation();
  t('i18n.route.admin.sports.source.health.redirect.probe');
  const router = useRouter();
  const { colors } = useTheme();

  useEffect(() => {
    router.replace('/admin-console?category=platform&tab=sports-source-health');
  }, [router]);

  return (
    <AppShell>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }} data-testid="sports-source-health-redirect" testID="sports-source-health-redirect">
        <ActivityIndicator color={colors.primary} />
      </View>
    </AppShell>
  );
}
