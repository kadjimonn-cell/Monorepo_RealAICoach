import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
export default function LocalMusicRedirect() {
  const { t } = useTranslation();
  t('i18n.route.mini-apps.local-music.probe');
  return <Redirect href="/features/ai-speech" />;
}