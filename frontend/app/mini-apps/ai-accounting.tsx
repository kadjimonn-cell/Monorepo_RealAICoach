import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
export default function AIAccountingRedirect() {
  const { t } = useTranslation();
  t('i18n.route.mini-apps.ai-accounting.probe');
  return <Redirect href="/features/pennypilot" />;
}