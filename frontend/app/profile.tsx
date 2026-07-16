import React from 'react';
import ProfileScreen from './(tabs)/profile';
import { useTranslation } from '../src/hooks/useTranslation';

export default function PublicProfileRoute() {
  const { t } = useTranslation();
  t('i18n.route.profile.probe');
  return <ProfileScreen />;
}