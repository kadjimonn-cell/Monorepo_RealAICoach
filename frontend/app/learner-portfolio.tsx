import React from 'react';

import AppShell from '../src/components/AppShell';
import { LearnerPortfolioScreen } from '../src/components/portfolio/LearnerPortfolioScreen';
import { useTranslation } from '../src/hooks/useTranslation';

export default function LearnerPortfolioPage() {
  const { t } = useTranslation();
  t('i18n.route.learner-portfolio.probe');
  return (
    <AppShell>
      <LearnerPortfolioScreen mode="private" />
    </AppShell>
  );
}