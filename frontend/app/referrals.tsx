import React, { Suspense } from 'react';
import { ReferralsSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

const LazyReferrals = React.lazy(() => import('../src/components/pages/ReferralsV2'));

export default function ReferralsPage() {
  const { t } = useTranslation();
  t('i18n.route.referrals.probe');
  return (
    <Suspense fallback={<ReferralsSkeleton />}>
      <LazyReferrals />
    </Suspense>
  );
}