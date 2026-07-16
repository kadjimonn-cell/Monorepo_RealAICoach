import React from 'react';
import SchoolTutorView from '../../src/components/SchoolTutorView';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function SchoolTutorScreen() {
  const { t } = useTranslation();
  t('i18n.route.features.school-tutor.probe');
  return <SchoolTutorView />;
}
