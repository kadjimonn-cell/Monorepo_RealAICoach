import React, { useEffect } from 'react';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { ProfileFormSkeleton } from '../../src/components/SkeletonLoaders';
import { useAuth } from '../../src/context/AuthContext';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

export default function AuthLogoutScreen() {
  const { t } = useTranslation();
  t('i18n.route.auth.logout.probe');
  const router = useRouter();
  const { logout } = useAuth();

  useEffect(() => {
    const run = async () => {
      try {
        await logout();
      } catch (error) { handleAppRecoverableError({ scope: 'auth/logout.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      try {
        await AsyncStorage.multiRemove(['session_token', 'guest_mode']);
      } catch (error) { handleAppRecoverableError({ scope: 'auth/logout.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

      if (typeof window !== 'undefined') {
        try {
          window.localStorage.removeItem('session_token');
          window.localStorage.removeItem('guest_mode');
          window.localStorage.removeItem('realtalk_user_id');
        } catch (error) { handleAppRecoverableError({ scope: 'auth/logout.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }

      router.replace('/auth/login?logout=1');
    };

    run();
  }, [logout, router]);

  return <ProfileFormSkeleton />;
}