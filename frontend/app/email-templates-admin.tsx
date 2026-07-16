import React from 'react';
import { Redirect } from 'expo-router';
import { useTranslation } from '../src/hooks/useTranslation';

export default function EmailTemplatesAdminStandalonePage() {
  const { t } = useTranslation();
  t('i18n.route.email-templates-admin.probe');
  return <Redirect href="/admin-console?category=comms&tab=email-templates" />;
}