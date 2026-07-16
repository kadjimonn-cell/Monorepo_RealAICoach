import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function AuthIndex() {
  const { t } = useTranslation();
  t('i18n.route.auth.index.probe');
  return <Redirect href="/auth/login" />;
}