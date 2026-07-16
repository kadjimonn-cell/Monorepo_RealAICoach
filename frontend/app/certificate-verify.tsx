import React from 'react';
import CertificateVerifyPage from './certificate-verify/[verificationId]';
import { useTranslation } from '../src/hooks/useTranslation';

export default function CertificateVerifyRoute() {
  const { t } = useTranslation();
  t('i18n.route.certificate-verify.probe');
  return <CertificateVerifyPage />;
}