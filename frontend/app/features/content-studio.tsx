import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function ContentStudioScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.content-studio.probe');
  return <Redirect href="/content-library" />;
}