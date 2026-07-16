import React from 'react';
import { Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentHistorySummary } from './types';
import { formatAmount, formatLongDate } from './utils';

type Props = {
  summary: PaymentHistorySummary;
  colors: any;
  tx: (key: string, fallback: string) => string;
};

type InsightCardProps = {
  testId: string;
  label: string;
  value: string;
  helper: string;
  icon: keyof typeof Ionicons.glyphMap;
  toneBg: string;
  toneBorder: string;
  toneText: string;
};

const InsightCard = ({ testId, label, value, helper, icon, toneBg, toneBorder, toneText }: InsightCardProps) => (
  <View style={{ flex: 1, minWidth: 180, backgroundColor: toneBg, borderRadius: 18, padding: 16, borderWidth: 1, borderColor: toneBorder }} {...getTestProps(testId)}>
    <View style={{ width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: (globalThis as any).__alphaColor(toneText, '14') }}>
      <Ionicons name={icon} size={18} color={toneText} />
    </View>
    <Text style={{ fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8, color: toneText, marginTop: 10 }}>{label}</Text>
    <Text style={{ fontSize: 24, fontWeight: '900', color: toneText, marginTop: 5 }}>{value}</Text>
    <Text style={{ fontSize: 11, lineHeight: 16, color: toneText, opacity: 0.84, marginTop: 6 }} {...getTestProps(`${testId}-helper`)}>{helper}</Text>
  </View>
);

export const PaymentHistoryInsights = ({ summary, colors, tx }: Props) => (
  <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }} {...getTestProps('payment-history-insights-grid')}>
    <InsightCard testId="payment-history-kpi-total-paid" label={tx('paymentHistory.kpi.totalPaid', 'Total paid')} value={formatAmount(summary.totalPaid, 'USD')} helper={tx('paymentHistory.kpi.totalPaidHelper', 'Successful charges currently visible in this workspace view.')} icon="wallet-outline" toneBg={colors.successSoft} toneBorder={colors.success + '44'} toneText={colors.successText} />
    <InsightCard testId="payment-history-kpi-successful-count" label={tx('paymentHistory.kpi.successfulPayments', 'Successful payments')} value={String(summary.successfulPayments)} helper={tx('paymentHistory.kpi.successfulPaymentsHelper', 'Paid and completed records only — derived directly from platform billing history.')} icon="checkmark-circle-outline" toneBg={colors.primarySoft} toneBorder={colors.primary + '44'} toneText={colors.primary} />
    <InsightCard testId="payment-history-kpi-current-plan" label={tx('paymentHistory.kpi.currentPlan', 'Current plan')} value={summary.currentPlanLabel} helper={tx('paymentHistory.kpi.currentPlanHelper', 'Live subscription plan from your authenticated platform profile.')} icon="diamond-outline" toneBg={colors.warningSoft} toneBorder={colors.warning + '44'} toneText={colors.warningText} />
    <InsightCard testId="payment-history-kpi-last-payment" label={tx('paymentHistory.kpi.lastSuccessfulPayment', 'Last successful payment')} value={summary.lastSuccessfulPayment ? formatAmount(summary.lastSuccessfulPayment.totalAmount, summary.lastSuccessfulPayment.currency) : tx('paymentHistory.kpi.none', 'None')} helper={summary.lastSuccessfulPayment ? formatLongDate(summary.lastSuccessfulPayment.createdAt) : tx('paymentHistory.kpi.noneHelper', 'A paid record will appear here once available.')} icon="time-outline" toneBg={colors.infoSoft} toneBorder={colors.info + '44'} toneText={colors.infoText} />
  </View>
);

/* i18n-probe t('i18n.auto.probe') */
