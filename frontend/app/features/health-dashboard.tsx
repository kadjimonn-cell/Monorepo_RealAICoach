import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
export default function HealthDashRedirect() {
  const { t } = useTranslation();
  t('i18n.route.features.health-dashboard.probe');
  return <Redirect href="/features/medimate" />;
}