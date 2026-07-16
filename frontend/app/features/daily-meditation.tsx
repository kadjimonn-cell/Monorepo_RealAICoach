import React from 'react';

import FeatureLayout from '../../src/components/FeatureLayout';
import DailyMeditationMain from '../../src/components/daily-meditation/DailyMeditationMain';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function DailyMeditationPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="daily-meditation"
      title={t('Daily Meditation')}
      subtitle={t('Faith-centered daily reflection, companion support, reminders, and progress')}
      icon="leaf"
      color={colors.primary}
      showActions={false}
      showSecondaryTabs={false}
      showTransparencyBanner={false}
      noPadding
      selfScrolling
    >
      <DailyMeditationMain />
    </FeatureLayout>
  );
}
