import { Redirect } from 'expo-router';
import { useGlobalPlatformState } from '../src/hooks/useGlobalPlatformState';
import { useTranslation } from '../src/hooks/useTranslation';

export default function FAQScreen() {
  const { t } = useTranslation();
  t('i18n.route.faq.probe');
  useGlobalPlatformState();
  return <Redirect href="/help" />;
}