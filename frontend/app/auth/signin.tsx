import React, { useEffect } from 'react';
import { useRouter } from 'expo-router';

/**
 * Redirect /auth/signin -> /auth/login
 * Some users may try to access signin instead of login.
 * This ensures a seamless experience.
 */
export default function SignInRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/auth/login');
  }, []);

  return null;
}
