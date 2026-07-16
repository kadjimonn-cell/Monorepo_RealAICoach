import IDVerificationPage from './id-verification';
import { useTranslation } from '../src/hooks/useTranslation';

export default function IdCheckerRoute() {
  const { t } = useTranslation();
  t('i18n.route.id-checker.probe');
  return <IDVerificationPage routeVariant="id-checker" />;
}