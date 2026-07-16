import { Stack } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
import { AdminRouteGate } from '../../src/components/auth/AdminRouteGate';

export default function AdminLayout() {
  const { t } = useTranslation();
  // t('i18n.route.admin._layout.probe'); // Commented out: synchronous probe causes global crash
  return (
    <AdminRouteGate returnTo="/admin">
      <Stack screenOptions={{ headerShown: false }} />
    </AdminRouteGate>
  );
}
