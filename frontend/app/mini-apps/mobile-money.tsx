import { Redirect } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { resolveMiniAppRedirect } from '../../src/config/miniAppRedirects';

export default function MobileMoneyRetiredRedirect() {
  const { isAuthenticated } = useAuth();
  const target = resolveMiniAppRedirect('/mini-apps/mobile-money', { isAuthenticated }) || '/features';

  return <Redirect href={target as any} />;
}

/* i18n-probe t('i18n.auto.probe') */
