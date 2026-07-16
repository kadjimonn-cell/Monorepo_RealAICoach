import { Stack } from 'expo-router';
import { ProtectedRouteGate } from '../../src/components/auth/ProtectedRouteGate';
import { useAuth } from '../../src/context/AuthContext';

export default function FeaturesLayout() {
  const { isAuthenticated, loading } = useAuth();
  // t('i18n.route.features._layout.probe'); // Commented out: was causing synchronous render crash

  return (
    <ProtectedRouteGate isLoading={loading} isAllowed={isAuthenticated} returnTo="/features">
      <Stack screenOptions={{ headerShown: false }} />
    </ProtectedRouteGate>
  );
}