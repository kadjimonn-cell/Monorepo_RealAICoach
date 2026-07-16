import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
export default function AIVisionRedirect() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-vision.probe');
  return <Redirect href="/features/ai-photo" />;
}