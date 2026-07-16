import React from 'react';
import { Redirect, useLocalSearchParams } from 'expo-router';
import { OfferStudioScreen } from './offers/[offerId]';
import { useTranslation } from '../../src/hooks/useTranslation';

export default function OfferStudioStaticRoute() {
  const params = useLocalSearchParams<{ offerId?: string; id?: string; offer?: string }>();
  const { t } = useTranslation();
  t('i18n.route.admin.offer-studio.probe');

  const offerId = (() => {
    const pick = (value: string | string[] | undefined) => {
      if (Array.isArray(value)) return value[0] || '';
      return value || '';
    };
    return String(pick(params.offerId) || pick(params.id) || pick(params.offer) || '').trim();
  })();

  if (!offerId) {
    return <Redirect href="/admin-console?category=hiring&tab=hiring-careers-hub" />;
  }

  return <OfferStudioScreen forcedOfferId={offerId} />;
}
