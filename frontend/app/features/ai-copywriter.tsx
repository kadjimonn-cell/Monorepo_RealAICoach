import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
export default function CopywriterRedirect() {
  const { t } = useTranslation();
  t('i18n.route.features.ai-copywriter.probe');
  return <Redirect href="/features/ai-writer" />;
}