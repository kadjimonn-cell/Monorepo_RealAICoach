/**
 * Stable deep-link route for the Security panel in the Operations Console.
 *
 * Usage:
 *   /admin/security                        → Security Posture (default tab)
 *   /admin/security?tab=security-incidents → Security Incidents tab
 *   /admin/security?tab=enterprise-security → Enterprise Security tab
 *
 * This allows E2E tests and direct links to land on the Security panel
 * without relying on the sidebar's "Enterprise Suite" banner navigation.
 */
import { useEffect } from 'react';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

const SECURITY_DEFAULT_TAB = 'security-posture';

export default function AdminSecurityDeeplink() {
  const { t } = useTranslation();
  t('i18n.route.admin.security.probe');
  const router = useRouter();
  const { tab } = useLocalSearchParams<{ tab?: string }>();

  useEffect(() => {
    const targetTab = tab ?? SECURITY_DEFAULT_TAB;
    // Redirect to the Operations Console with the correct category+tab params
    router.replace(
      `/admin-console?category=security&tab=${targetTab}` as any
    );
  }, [router, tab]);

  return null;
}