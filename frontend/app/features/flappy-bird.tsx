import React from 'react';

import FeatureLayout from '../../src/components/FeatureLayout';
import FlappyBirdHub from '../../src/components/flappyBird/FlappyBirdHub';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function FlappyBirdPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="flappy-bird"
      title={t('Flappy Bird Game')}
      subtitle={t('Classic arcade flying challenge with a global leaderboard')}
      icon="paper-plane"
      color={colors.primary}
      showActions={false}
      showSecondaryTabs={false}
      showTransparencyBanner={false}
    >
      <FlappyBirdHub />
    </FeatureLayout>
  );
}
