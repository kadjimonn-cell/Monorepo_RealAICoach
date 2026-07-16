import React from 'react';
import LoginInner from '../../src/components/pages/LoginInner';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function LoginScreen() {
  const { t } = useTranslation();
  t('i18n.route.auth.login.probe');
  return <LoginInner />;
}