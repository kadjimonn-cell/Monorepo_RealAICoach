import React, { useEffect } from 'react';
import { StyleSheet} from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { ProfileFormSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

export default function LogoutScreen() {
  const { t } = useTranslation();
  t('i18n.route.logout.probe');
  const router = useRouter();
  const { _colors } = useTheme();
  const { logout } = useAuth();

  useEffect(() => {
    const performLogout = async () => {
      try {
        await logout();
      } catch (error) {
        console.error('Logout error:', error);
      }

      try {
        await AsyncStorage.multiRemove(['session_token', 'guest_mode']);
      } catch (error) {
        console.error('Logout storage error:', error);
      }

      if (typeof window !== 'undefined') {
        window.localStorage.removeItem('session_token');
        window.localStorage.removeItem('guest_mode');
        window.localStorage.removeItem('realtalk_user_id');
      }

      router.replace('/auth/login?logout=1');
    };

    performLogout();
  }, [logout, router]);

  return (
    <ProfileFormSkeleton />
  );
}

const _styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  message: {
    fontSize: 16,
    fontWeight: '600',
  },
});