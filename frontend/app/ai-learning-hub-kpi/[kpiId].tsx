import React from 'react';
import { Stack, useLocalSearchParams } from 'expo-router';

import AppShell from '../../src/components/AppShell';
import { EnterpriseLearningHubScreen } from '../../src/components/learning-hub/EnterpriseLearningHubScreen';
import { useTranslation } from '../../src/hooks/useTranslation';

const titleByKpi: Record<string, string> = {
  streak: 'KPI Detail · Streak Days',
  active: 'KPI Detail · Active Courses',
  complete: 'KPI Detail · Completed Courses',
  minutes: 'KPI Detail · Weekly Minutes',
};

export default function AILearningHubKpiRoute() {
  const { t } = useTranslation();
  t('i18n.route.ai-learning-hub-kpi.[kpiId].probe');
  const params = useLocalSearchParams<{ kpiId?: string }>();
  const slug = typeof params.kpiId === 'string' ? params.kpiId.toLowerCase() : 'streak';
  const headerTitle = titleByKpi[slug] || 'KPI Detail · AI Learning Hub';

  return (
    <AppShell>
      <Stack.Screen options={{ title: headerTitle }} />
      <EnterpriseLearningHubScreen />
    </AppShell>
  );
}