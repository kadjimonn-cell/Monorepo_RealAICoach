import React from 'react';
import { Platform } from 'react-native';

import { WebOnlyScreen } from '../../src/components/WebOnlyScreen';
import FeatureLayout from '../../src/components/FeatureLayout';
import FpsGameHub from '../../src/components/fpsGame/FpsGameHub';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function FpsGamePage() {
  if (Platform.OS !== 'web') {
    return <WebOnlyScreen featureNameKey="webOnly.fpsGame" featureNameFallback="FPS Game" />;
  }
  const { colors } = useTheme();
  const { t } = useLanguage();

  return (
    <FeatureLayout
      feature="games-station"
      title={t('FPS Game')}
      subtitle={t('Multiplayer first-person shooter arena')}
      icon="locate"
      color={colors.primary}
      showActions={false}
      showSecondaryTabs={false}
      showTransparencyBanner={false}
    >
      <FpsGameHub />
    </FeatureLayout>
  );
}
