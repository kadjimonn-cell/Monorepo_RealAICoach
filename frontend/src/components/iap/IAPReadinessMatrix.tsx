import React from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';

type Props = {
  colors: any;
  readinessRows: any[];
  tx: (key: string, fallback: string) => string;
};

export const IAPReadinessMatrix = ({ colors, readinessRows, tx }: Props) => (
  <BillingSectionCard colors={colors} testId="iap-readiness-card" style={{ flex: 1, minWidth: 280 }}>
    <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('iap-gateway-readiness-title')}>
      {tx('mobileSubscriptions.readiness.title', 'Gateway Readiness Matrix')}
    </Text>
    <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }}>
      {tx('mobileSubscriptions.readiness.subtitle', 'Apple App Store and Google Play readiness with explicit Live/Test/Sandbox visibility.')}
    </Text>

    <View style={{ gap: 10, marginTop: 14 }}>
      {readinessRows.length === 0 ? (
        <Text style={{ color: colors.textMuted, fontSize: 12 }} {...getTestProps('iap-readiness-empty-state')}>
          {tx('mobileSubscriptions.readiness.empty', 'No provider readiness data available.')}
        </Text>
      ) : readinessRows.map((row: any, idx: number) => {
        const state = String(row?.readiness_state || '').toLowerCase();
        const tone = state.includes('live') ? colors.success : state.includes('sandbox') || state.includes('test') ? colors.warning : colors.error;
        const icon = String(row?.provider || '').includes('apple') ? 'logo-apple' : 'logo-google-playstore';
        return (
          <View key={`${row?.provider || idx}`} style={{ borderRadius: 14, borderWidth: 1, borderColor: `${tone}55`, backgroundColor: `${tone}15`, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 12 }} {...getTestProps(`gateway-${row?.provider || idx}-ready`)}>
            <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: `${tone}16`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={icon as any} size={20} color={tone} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: tone, fontSize: 12, fontWeight: '800' }}>{row?.label || row?.provider || tx('mobileSubscriptions.readiness.providerFallback', 'IAP Provider')}</Text>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 3 }}>{row?.status_label || tx('mobileSubscriptions.readiness.unavailable', 'Unavailable')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 4 }}>{row?.message || tx('mobileSubscriptions.readiness.signalUnavailable', 'Readiness signal unavailable.')}</Text>
            </View>
            <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: `${tone}18`, borderWidth: 1, borderColor: `${tone}44` }}>
              <Text style={{ color: tone, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{row?.mode || tx('mobileSubscriptions.defaults.unknown', 'unknown')}</Text>
            </View>
          </View>
        );
      })}
    </View>
  </BillingSectionCard>
);

/* i18n-probe t('i18n.auto.probe') */
