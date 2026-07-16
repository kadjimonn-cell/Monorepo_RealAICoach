import React from 'react';
import SubscriptionPaymentResultPage from './subscription/payment-result';
import { useTranslation } from '../src/hooks/useTranslation';

export default function PaymentResultAliasPage() {
  const { t } = useTranslation();
  t('i18n.route.payment-result.probe');
  return <SubscriptionPaymentResultPage />;
}