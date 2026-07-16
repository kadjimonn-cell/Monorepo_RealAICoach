import React from 'react';
import AppShell from '../src/components/AppShell';
import { EnterpriseLearningHubScreen } from '../src/components/learning-hub/EnterpriseLearningHubScreen';
import { useTranslation } from '../src/hooks/useTranslation';
import { useAuth } from '../src/context/AuthContext';
import { ProtectedRouteGate } from '../src/components/auth/ProtectedRouteGate';

export default function AILearningHubScreen() {
  const { t } = useTranslation();
  const { user, loading: authLoading } = useAuth();
  t('i18n.route.ai-learning-hub.probe');
  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={Boolean(user?.user_id)} returnTo="/ai-learning-hub">
      <AppShell>
        <EnterpriseLearningHubScreen />
      </AppShell>
    </ProtectedRouteGate>
  );
}