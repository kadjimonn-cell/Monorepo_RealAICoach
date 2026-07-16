import React from 'react';
import { View } from 'react-native';
import AppShell from '../src/components/AppShell';
import { EmployerPortalContent } from './employer-apply';
import { useTranslation } from '../src/hooks/useTranslation';

export default function EmployerConsolePage() {
  const { t } = useTranslation();
  t('i18n.route.employer-console.probe');
  return (
    <AppShell>
      <View style={{ flex: 1, backgroundColor: 'transparent' }} data-testid="employer-console-page" testID="employer-console-page">
        <EmployerPortalContent />
      </View>
    </AppShell>
  );
}