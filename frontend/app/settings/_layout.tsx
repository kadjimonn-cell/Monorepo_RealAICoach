import { Stack } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function SettingsLayout() {
  const { t } = useTranslation();
  // t('i18n.route.settings._layout.probe'); // Commented out: synchronous probe causes global crash
  return <Stack screenOptions={{ headerShown: false }} />;
}
