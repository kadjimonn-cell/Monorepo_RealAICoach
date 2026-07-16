import React from 'react';
import FeatureLayout from '../../src/components/FeatureLayout';
import SportsFeature30 from '../../src/components/feature30/SportsFeature30';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function SportsPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="sports"
      title={t('Sports')}
      subtitle="Live rails, league loops, and instant watch continuity"
      icon="american-football"
      color={colors.primary}
      showActions={false}
      showTransparencyBanner={false}
      showSecondaryTabs={false}
    >
      <SportsFeature30 />
    </FeatureLayout>
  );
}
