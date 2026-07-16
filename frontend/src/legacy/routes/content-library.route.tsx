import React from 'react';
import { Redirect } from 'expo-router';
import { useTranslation } from '../src/hooks/useTranslation';

export default function PublicContentLibraryRoute() {
  const { t } = useTranslation();
  t('i18n.route.content-library.probe');
  return <Redirect href="/(tabs)/content-library" />;
}