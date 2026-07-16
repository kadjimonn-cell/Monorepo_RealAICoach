import React from 'react';
import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function MiniAppsIndexRedirect() {
  const { t } = useTranslation();
  t('i18n.route.mini-apps.index.probe');
  return <Redirect href="/features" />;
}