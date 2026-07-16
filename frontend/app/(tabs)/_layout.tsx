import React from 'react';
import { Tabs, usePathname } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';
import { ProtectedRouteGate } from '../../src/components/auth/ProtectedRouteGate';

export default function TabLayout() {
  const { isAuthenticated, loading, user } = useAuth();
  const pathname = usePathname();
  // t('i18n.route.(tabs)._layout.probe'); // Commented out: synchronous probe causes global crash
  // Bottom tab bar is fully replaced by the sidebar/drawer navigation.
  // Tabs component retained solely for expo-router screen registration.

  const isAdmin = hasAdminConsoleVisibility(user);

  return (
    <ProtectedRouteGate
      isLoading={loading}
      isAllowed={isAuthenticated}
      returnTo={pathname || '/dashboard'}
      requireFreshServerSession
    >
      <Tabs
        sceneContainerStyle={{ backgroundColor: 'transparent' }}
        screenOptions={{ headerShown: false, tabBarStyle: { display: 'none' } }}
      >
        <Tabs.Screen name="index" options={{ title: 'Home' }} />
        <Tabs.Screen name="practice" options={{ title: 'Practice' }} />
        <Tabs.Screen name="progress" options={{ title: 'Progress' }} />
        <Tabs.Screen name="downloads" options={{ title: 'Downloads' }} />
        {isAdmin ? <Tabs.Screen name="admin-console" options={{ title: 'Operations Console' }} /> : null}
        <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
      </Tabs>
    </ProtectedRouteGate>
  );
}
