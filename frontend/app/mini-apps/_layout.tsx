import { Stack, usePathname, useRouter } from 'expo-router';
import { useEffect } from 'react';
import { resolveMiniAppRedirect } from '../../src/config/miniAppRedirects';
import { useAuth } from '../../src/context/AuthContext';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function MiniAppsLayout() {
  useTranslation();
  // t('i18n.route.mini-apps._layout.probe'); // Commented out: synchronous probe causes global crash
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const target = resolveMiniAppRedirect(pathname, { isAuthenticated });
    if (!target || target === pathname) return;
    router.replace(target as any);
  }, [isAuthenticated, pathname, router]);

  return <Stack screenOptions={{ headerShown: false }} />;
}
