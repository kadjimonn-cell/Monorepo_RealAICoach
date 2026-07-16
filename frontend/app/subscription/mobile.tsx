import AppShell from '../../src/components/AppShell';
import MobileSubscriptionsView from '../../src/components/MobileSubscriptionsViewV2';
import { PricingSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function MobileSubscriptionsPage() {
  const { t } = useTranslation();
  t('i18n.route.subscription.mobile.probe');
  const pageReady = usePageReady();
  if (!pageReady) return <PricingSkeleton />;

  return (
    <AppShell>
      <MobileSubscriptionsView />
    </AppShell>
  );
}