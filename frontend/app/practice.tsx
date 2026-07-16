import React from 'react';
import PracticeScreen from './(tabs)/practice';
import { useTranslation } from '../src/hooks/useTranslation';

export default function PublicPracticeRoute() {
  const { t } = useTranslation();
  t('i18n.route.practice.probe');
  return <PracticeScreen />;
}