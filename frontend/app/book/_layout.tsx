import { Stack } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function BookLayout() {
  const { t } = useTranslation();
  // t('i18n.route.book._layout.probe'); // Commented out: synchronous probe causes global crash
  return <Stack screenOptions={{ headerShown: false }} />;
}
