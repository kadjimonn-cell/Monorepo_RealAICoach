import React from 'react';
import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function AdminEmailTemplatesRoute() {
  const { t } = useTranslation();
  t('i18n.route.admin.email-templates.probe');
  return <Redirect href="/admin-console?category=comms&tab=email-templates" />;
}