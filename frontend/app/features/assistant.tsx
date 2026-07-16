import React from 'react';
import { View, Text } from 'react-native';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { FeatureDetailSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

export default function AssistantScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.assistant.probe');
  const pageReady = usePageReady();
  const { user } = useAuth();
  const { colors } = useTheme();
  const isAdmin = hasAdminConsoleVisibility(user as any);

  if (!isAdmin) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: colors.bg }} data-testid="assistant-unauthorized" testID="assistant-unauthorized">
        <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700', marginBottom: 8 }}>403 Forbidden</Text>
        <Text style={{ color: colors.textMuted, textAlign: 'center' }}>Safe Backend is now available only inside the Admin Console.</Text>
      </View>
    );
  }

  if (!pageReady) return <FeatureDetailSkeleton />;
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: colors.bg }} data-testid="assistant-admin-redirect" testID="assistant-admin-redirect">
      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '700', marginBottom: 8 }}>Safe Backend</Text>
      <Text style={{ color: colors.textMuted, textAlign: 'center' }}>Access the Safe Backend tools from the Admin Console.</Text>
    </View>
  );
}