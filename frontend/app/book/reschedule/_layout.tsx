import { Stack } from 'expo-router';
import { useTranslation } from '../../../src/hooks/useTranslation';

export default function RescheduleLayout() {
  const { t } = useTranslation();
  t('i18n.route.book.reschedule._layout.probe');
  return <Stack screenOptions={{ headerShown: false }} />;
}