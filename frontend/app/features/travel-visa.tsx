import React from 'react';
import FeatureLayout from '../../src/components/FeatureLayout';
import TravelVisaMain from '../../src/components/travel-visa/TravelVisaMain';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function TravelVisaPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="travel-visa"
      title={t('Travel Visa')}
      subtitle={t('AI-Powered Visa Coaching')}
      icon="airplane"
      color={colors.primary}
      showActions={false}
      showTransparencyBanner={false}
      showSecondaryTabs={false}
      noPadding
      selfScrolling
    >
      <TravelVisaMain />
    </FeatureLayout>
  );
}
