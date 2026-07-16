import React from 'react';

import FeatureLayout from '../../src/components/FeatureLayout';
import FpsGameHub from '../../src/components/fpsGame/FpsGameHub';
import { useTheme } from '../../src/context/ThemeContext';
import { useLanguage } from '../../src/i18n/LanguageContext';

export default function FpsGamePage() {
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
