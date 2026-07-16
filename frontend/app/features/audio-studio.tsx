import React from 'react';
import FeatureLayout from '../../src/components/FeatureLayout';
import AudioStudioFeature28 from '../../src/components/feature28/AudioStudioFeature28';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function AudioStudioPage() {
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="audio-studio"
      title={t('Audio Studio')}
      subtitle=""
      icon="musical-notes"
      color={colors.primary}
      showActions={false}
      showTransparencyBanner={false}
      showSecondaryTabs={false}
    >
      <AudioStudioFeature28 />
    </FeatureLayout>
  );
}
