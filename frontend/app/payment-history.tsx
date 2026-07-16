import React, { Suspense } from 'react';
import { PaymentHistorySkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

const LazyPaymentHistory = React.lazy(() => import('../src/components/pages/PaymentHistoryV2'));

export default function PaymentHistoryScreen() {
  const { t } = useTranslation();
  t('i18n.route.payment-history.probe');
  return (
    <Suspense fallback={<PaymentHistorySkeleton />}>
      <LazyPaymentHistory />
    </Suspense>
  );
}