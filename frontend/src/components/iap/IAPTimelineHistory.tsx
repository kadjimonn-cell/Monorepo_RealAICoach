import React from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { BillingSectionCard } from '../paymentHistory/BillingRoutePrimitives';
import { formatAmount, formatLongDate } from '../paymentHistory/utils';

type Props = {
  colors: any;
  timeline: any[];
  history: any[];
  tx: (key: string, fallback: string) => string;
};

export const IAPTimelineHistory = ({ colors, timeline, history, tx }: Props) => (
  <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
    <BillingSectionCard colors={colors} testId="iap-timeline-card" style={{ flex: 0.95, minWidth: 280 }}>
      <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('mobile-subscription-timeline-card')}>
        {tx('mobileSubscriptions.timeline.title', 'Subscription Timeline')}
      </Text>
      {(timeline || []).length === 0 ? (
        <View style={{ marginTop: 16, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 16 }} {...getTestProps('mobile-subscription-timeline-empty')}>
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('mobileSubscriptions.timeline.empty', 'No timeline events yet.')}</Text>
        </View>
      ) : (
        <View style={{ gap: 10, marginTop: 16 }}>
          {timeline.slice(0, 8).map((event: any, idx: number) => (
            <View key={`${event.event_id || idx}`} style={{ flexDirection: 'row', gap: 12 }} {...getTestProps(`mobile-subscription-timeline-event-${idx}`)}>
              <View style={{ alignItems: 'center' }}>
                <View style={{ width: 14, height: 14, borderRadius: 999, backgroundColor: colors.primary, marginTop: 6 }} />
                {idx < timeline.slice(0, 8).length - 1 && <View style={{ width: 2, flex: 1, backgroundColor: colors.border, marginTop: 6 }} />}
              </View>
              <View style={{ flex: 1, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12, marginBottom: 6 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', textTransform: 'uppercase' }}>{event.event_type || tx('mobileSubscriptions.timeline.defaults.update', 'update')}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 6 }}>{tx('mobileSubscriptions.timeline.changeLine', 'From: {from} → To: {to} • Status: {status}').replace('{from}', String(event.from_plan || tx('mobileSubscriptions.defaults.freeLower', 'free'))).replace('{to}', String(event.to_plan || tx('mobileSubscriptions.defaults.freeLower', 'free'))).replace('{status}', String(event.status || tx('mobileSubscriptions.status.activeLower', 'active')))}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6 }}>{tx('mobileSubscriptions.timeline.effective', 'Effective')}: {event.effective_at ? new Date(event.effective_at).toLocaleString() : '-'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </BillingSectionCard>

    <BillingSectionCard colors={colors} testId="iap-history-card" style={{ flex: 1.35, minWidth: 320 }}>
      <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('mobile-subs-history')}>
        {tx('mobileSubscriptions.history.title', 'Purchase History')}
      </Text>
      {history.length === 0 ? (
        <View style={{ alignItems: 'center', paddingVertical: 34 }} {...getTestProps('mobile-subs-history-empty')}>
          <Ionicons name="receipt-outline" size={34} color={colors.textMuted} />
          <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 10 }}>{tx('mobileSubscriptions.history.empty', 'No in-app purchases yet')}</Text>
        </View>
      ) : (
        <View style={{ marginTop: 16 }}>
          <View style={{ flexDirection: 'row', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border }}>
            {['Date', 'Invoice', 'Plan', 'Amount', 'Status'].map((label) => (
              <Text key={label} style={{ flex: 1, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{label}</Text>
            ))}
          </View>
          {history.map((item, index) => (
            <View key={`${item.transaction_id || index}`} style={{ flexDirection: 'row', paddingVertical: 12, borderBottomWidth: index === history.length - 1 ? 0 : 1, borderBottomColor: colors.border, alignItems: 'flex-start' }} {...getTestProps(`mobile-tx-${index}`)}>
              <Text style={{ flex: 1, color: colors.text, fontSize: 11 }}>{item.created_at ? formatLongDate(item.created_at) : '—'}</Text>
              <Text style={{ flex: 1, color: colors.text, fontSize: 11 }}>{item.transaction_id || '—'}</Text>
              <Text style={{ flex: 1, color: colors.text, fontSize: 11 }}>{`${String(item.plan || 'free').charAt(0).toUpperCase()}${String(item.plan || '').slice(1)} · ${String(item.period || '').toLowerCase()}`}</Text>
              <Text style={{ flex: 1, color: colors.text, fontSize: 11 }}>{formatAmount(Number(item.total_amount || item.amount_gross || item.amount || 0), item.currency || 'USD')}</Text>
              <Text style={{ flex: 1, color: String(item.status || '').toLowerCase() === 'active' ? colors.successText : colors.warningText, fontSize: 11, fontWeight: '800' }}>{item.status || '—'}</Text>
            </View>
          ))}
        </View>
      )}
    </BillingSectionCard>
  </View>
);

/* i18n-probe t('i18n.auto.probe') */
