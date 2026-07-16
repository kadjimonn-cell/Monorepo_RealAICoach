/**
 * Stable deep-link route for Talent Network admin operations tab.
 *
 * Usage:
 *   /admin/talent-network
 *
 * Behavior:
 * - If not authenticated: redirect to login with return_to target
 * - If authenticated admin: open Operations Console at talent-network-admin tab
 */
import { useEffect } from 'react';
import { useRouter } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

const TARGET_OPS_TAB = '/admin-console?category=hiring&tab=talent-network-admin';

export default function AdminTalentNetworkDeeplink() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;

    if (!user) {
      const qs = new URLSearchParams();
      qs.set('return_to', TARGET_OPS_TAB);
      qs.set('auth_reason', 'admin_deeplink');
      router.replace((`/auth/login?${qs.toString()}`) as any);
      return;
    }

    if (!hasAdminConsoleVisibility(user as any)) {
      router.replace('/welcome' as any);
      return;
    }

    router.replace(TARGET_OPS_TAB as any);
  }, [loading, router, user]);

  return null;
}
