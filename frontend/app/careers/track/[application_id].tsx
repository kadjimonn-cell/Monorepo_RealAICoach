import React, { useEffect } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useTheme } from '../../../src/context/ThemeContext';
import { useLanguage } from '../../../src/i18n/LanguageContext';

export default function CareersTrackerRouteBridge() {
  const { t } = useLanguage();
  const router = useRouter();
  const { colors } = useTheme();
  const params = useLocalSearchParams<{ application_id?: string | string[] }>();

  const applicationIdRaw = params?.application_id;
  const applicationId = Array.isArray(applicationIdRaw)
    ? String(applicationIdRaw[0] || '').trim()
    : String(applicationIdRaw || '').trim();

  useEffect(() => {
    if (!applicationId) {
      router.replace('/track-application' as any);
      return;
    }
    router.replace(`/track-application?id=${encodeURIComponent(applicationId)}` as any);
  }, [applicationId, router]);

  return (
    <View
      style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bg, padding: 20 }}
      data-testid="careers-track-route-bridge"
      testID="careers-track-route-bridge"
    >
      <ActivityIndicator color={colors.primary} />
      <Text
        style={{ color: colors.textSec, fontSize: 13, marginTop: 10, textAlign: 'center' }}
        data-testid="careers-track-route-bridge-text"
        testID="careers-track-route-bridge-text"
      >{t("adopt.redirecting.to.application.tracker")}</Text>
    </View>
  );
}
