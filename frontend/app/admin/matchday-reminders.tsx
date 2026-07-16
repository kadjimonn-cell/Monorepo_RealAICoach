import React, { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useRouter } from 'expo-router';
import AppShell from '../../src/components/AppShell';
import { useTheme } from '../../src/context/ThemeContext';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function MatchdayRemindersPage() {
  const { t } = useTranslation();
  t('i18n.route.admin.matchday.reminders.redirect.probe');
  const router = useRouter();
  const { colors } = useTheme();

  useEffect(() => {
    router.replace('/admin-console?category=platform&tab=matchday-reminders');
  }, [router]);

  return (
    <AppShell>
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }} data-testid="matchday-reminders-redirect" testID="matchday-reminders-redirect">
        <ActivityIndicator color={colors.primary} />
      </View>
    </AppShell>
  );
}
