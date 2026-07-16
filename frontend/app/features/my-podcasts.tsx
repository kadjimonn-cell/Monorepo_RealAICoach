import React from 'react';
import FeatureLayout from '../../src/components/FeatureLayout';
import PodcastsFeature29 from '../../src/components/feature29/PodcastsFeature29';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function MyPodcastsPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="my-podcasts"
      title={t('My Podcasts')}
      subtitle={t('Auto-curated podcast feed with smart binge flow')}
      icon="mic"
      color={colors.primary}
      showActions={false}
      showTransparencyBanner={false}
      showSecondaryTabs={false}
    >
      <PodcastsFeature29 />
    </FeatureLayout>
  );
}
