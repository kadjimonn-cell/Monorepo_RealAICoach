import React from 'react';
import { View} from 'react-native';
import BuySmartHomeView from '../../src/components/BuySmartHomeView';
import { FeatureDetailSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function SmartHomeFeatureScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.buy-smart-home.probe');
  const pageReady = usePageReady();

  if (!pageReady) return <FeatureDetailSkeleton />;
  return (
    <View style={{ flex: 1 }}>
      <BuySmartHomeView />
    </View>
  );
}