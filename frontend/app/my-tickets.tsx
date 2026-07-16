import React, { Suspense } from 'react';
import { TicketsSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

const LazyMyTickets = React.lazy(() => import('../src/components/pages/MyTicketsInner'));

export default function MyTicketsScreen() {
  const { t } = useTranslation();
  t('i18n.route.my-tickets.probe');
  return (
    <Suspense fallback={<TicketsSkeleton />}>
      <LazyMyTickets />
    </Suspense>
  );
}