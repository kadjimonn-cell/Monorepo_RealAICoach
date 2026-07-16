import React, { Suspense } from 'react';
import { AgendaSkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';

const LazyCalendar = React.lazy(() => import('../src/components/pages/CalendarInner'));

export default function CalendarScreen() {
  const { t } = useTranslation();
  t('i18n.route.calendar.probe');
  return (
    <Suspense fallback={<AgendaSkeleton />}>
      <LazyCalendar />
    </Suspense>
  );
}