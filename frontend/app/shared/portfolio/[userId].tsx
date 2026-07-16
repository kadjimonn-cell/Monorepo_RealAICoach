import React from 'react';
import { useLocalSearchParams } from 'expo-router';

import { LearnerPortfolioScreen } from '../../../src/components/portfolio/LearnerPortfolioScreen';
import { useTranslation } from '../../../src/hooks/useTranslation';

export default function PublicLearnerPortfolioPage() {
  const { t } = useTranslation();
  t('i18n.route.shared.portfolio.[userId].probe');
  const params = useLocalSearchParams<{ userId?: string }>();
  const userId = typeof params.userId === 'string' ? params.userId : '';

  return <LearnerPortfolioScreen mode="public" userId={userId} />;
}