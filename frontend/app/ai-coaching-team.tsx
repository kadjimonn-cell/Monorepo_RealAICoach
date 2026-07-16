import React from 'react';
import CoachingTeamPage from '../src/components/pages/CoachingTeamPage';
import { useTranslation } from '../src/hooks/useTranslation';

export default function AICoachingTeamRoute() {
  const { t } = useTranslation();
  t('i18n.route.ai-coaching-team.probe');
  return <CoachingTeamPage />;
}
