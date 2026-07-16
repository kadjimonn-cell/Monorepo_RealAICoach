import React from 'react';
import { Redirect } from 'expo-router';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useAuth } from '../../src/context/AuthContext';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

export default function AdminIndexRedirect() {
  const { t } = useTranslation();
  const { user } = useAuth();
  t('i18n.route.admin.index.probe');
  if (!hasAdminConsoleVisibility(user as any)) {
    return <Redirect href="/dashboard" />;
  }
  return <Redirect href="/admin-console" />;
}