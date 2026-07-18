import React from 'react';
import { Platform } from 'react-native';
import { Tabs, usePathname } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';
import { ProtectedRouteGate } from '../../src/components/auth/ProtectedRouteGate';

const isWeb = Platform.OS === 'web';

function tabIcon(name: keyof typeof Ionicons.glyphMap) {
  return ({ color, size }: { color: string; size: number }) => (
    <Ionicons name={name} size={size} color={color} />
  );
}

export default function TabLayout() {
  const { isAuthenticated, loading, user } = useAuth();
  const pathname = usePathname();
  const { colors } = useTheme();
  // t('i18n.route.(tabs)._layout.probe'); // Commented out: synchronous probe causes global crash
  // Web: bottom tab bar is fully replaced by the sidebar/drawer navigation (hidden).
  // Native: real bottom tab bar for platform-appropriate navigation.

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
        screenOptions={{
          headerShown: false,
          tabBarStyle: isWeb
            ? { display: 'none' }
            : { backgroundColor: colors.surface, borderTopColor: colors.border },
          tabBarActiveTintColor: colors.primary,
          tabBarInactiveTintColor: colors.textMuted,
        }}
      >
        <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: tabIcon('home-outline') }} />
        <Tabs.Screen name="practice" options={{ title: 'Practice', tabBarIcon: tabIcon('mic-outline') }} />
        <Tabs.Screen name="progress" options={{ title: 'Progress', tabBarIcon: tabIcon('trending-up-outline') }} />
        <Tabs.Screen name="downloads" options={{ title: 'Downloads', tabBarIcon: tabIcon('download-outline') }} />
        {isAdmin ? (
          <Tabs.Screen
            name="admin-console"
            options={{ title: 'Operations Console', tabBarItemStyle: isWeb ? undefined : { display: 'none' } }}
          />
        ) : null}
        <Tabs.Screen name="profile" options={{ title: 'Profile', tabBarIcon: tabIcon('person-outline') }} />
      </Tabs>
    </ProtectedRouteGate>
  );
}
