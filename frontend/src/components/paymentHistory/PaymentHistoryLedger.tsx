import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentHistoryRecord } from './types';
import { formatAmount, formatShortDate } from './utils';

type Props = {
  colors: any;
  tx: (key: string, fallback: string) => string;
  records: PaymentHistoryRecord[];
  isWide: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: () => void;
  onOpenDetails: (record: PaymentHistoryRecord) => void;
};

const getStatusTone = (status: string, colors: any) => {
  if (status === 'paid') return { bg: colors.successSoft, border: colors.success + '44', text: colors.successText };
  if (status === 'pending') return { bg: colors.warningSoft, border: colors.warning + '44', text: colors.warningText };
  if (status === 'failed') return { bg: colors.errorSoft || colors.bgSoft, border: colors.error + '44', text: colors.error };
  return { bg: colors.bgSoft, border: colors.border, text: colors.textMuted };
};

const gatewayLabel = (gatewayKey: string) => {
  if (gatewayKey === 'paypal') return 'PayPal';
  if (gatewayKey === 'fedapay') return 'FedaPay';
  if (gatewayKey === 'stripe') return 'Stripe';
  return gatewayKey || 'Gateway';
};

export const PaymentHistoryLedger = ({ colors, tx, records, isWide, selectedIds, onToggleSelect, onToggleSelectAll, onOpenDetails }: Props) => {
  const selectableRecords = records.filter((record) => record.documentId);

  return (
    <View style={{ backgroundColor: colors.card, borderRadius: 20, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }} {...getTestProps('payment-history-ledger')}>
      <View style={{ paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('payment-history-ledger-title')}>{tx('paymentHistory.ledger.title', 'Payment ledger')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }} {...getTestProps('payment-history-ledger-subtitle')}>{tx('paymentHistory.ledger.subtitle', 'Click a row to open the enterprise detail panel with receipts, invoices, and payment breakdowns.')}</Text>
        </View>

        {selectableRecords.length > 0 && (
          <TouchableOpacity onPress={onToggleSelectAll} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} {...getTestProps('payment-history-select-all-button')} accessibilityLabel="checkmark button">
            <View style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: selectedIds.size > 0 ? colors.text : colors.textMuted, backgroundColor: selectedIds.size > 0 ? colors.text : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
              {selectedIds.size > 0 && <Ionicons name="checkmark" size={12} color={colors.bg} />}
            </View>
            <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '800' }}>{selectedIds.size > 0 ? `${selectedIds.size} ${tx('paymentHistory.ledger.selected', 'selected')}` : tx('paymentHistory.ledger.selectAll', 'Select all')}</Text>
          </TouchableOpacity>
        )}
      </View>

      {isWide ? (
        <View>
          <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: colors.bgSoft, borderBottomWidth: 1, borderBottomColor: colors.border }} {...getTestProps('payment-history-table-header')}>
            <Text style={{ flex: 0.8, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.select', 'Select')}</Text>
            <Text style={{ flex: 1.3, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.date', 'Date')}</Text>
            <Text style={{ flex: 2.4, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.description', 'Invoice / description')}</Text>
            <Text style={{ flex: 1.2, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.gateway', 'Gateway')}</Text>
            <Text style={{ flex: 1.1, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.amount', 'Amount')}</Text>
            <Text style={{ flex: 1, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.status', 'Status')}</Text>
            <Text style={{ flex: 1.1, color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.actions', 'Actions')}</Text>
          </View>

          {records.map((record, index) => {
            const statusTone = getStatusTone(record.status, colors);
            return (
              <TouchableOpacity key={record.id} onPress={() => onOpenDetails(record)} accessibilityLabel={formatShortDate(record.createdAt)} style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 14, alignItems: 'center', borderBottomWidth: index === records.length - 1 ? 0 : 1, borderBottomColor: colors.border, backgroundColor: selectedIds.has(record.documentId) ? colors.primarySoft : 'transparent' }} {...getTestProps(`payment-history-row-${index}`)}>
                <View style={{ flex: 0.8 }}>
                  <TouchableOpacity onPress={() => onToggleSelect(record.documentId)} accessibilityLabel={formatShortDate(record.createdAt)} disabled={!record.documentId} style={{ width: 20, height: 20, borderRadius: 5, borderWidth: 1.5, borderColor: selectedIds.has(record.documentId) ? colors.text : colors.textMuted, backgroundColor: selectedIds.has(record.documentId) ? colors.text : 'transparent', alignItems: 'center', justifyContent: 'center', opacity: record.documentId ? 1 : 0.35 }} {...getTestProps(`payment-history-row-select-${index}`)}>
                    {selectedIds.has(record.documentId) && <Ionicons name="checkmark" size={14} color={colors.bg} />}
                  </TouchableOpacity>
                </View>
                <View style={{ flex: 1.3 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{formatShortDate(record.createdAt)}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }}>{record.sourceLabel}</Text>
                </View>
                <View style={{ flex: 2.4, paddingRight: 10 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} numberOfLines={1} {...getTestProps(`payment-history-row-reference-${index}`)}>{record.referenceId}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} numberOfLines={1}>{record.planLabel} · {record.billingPeriod || tx('paymentHistory.ledger.noPeriod', 'No billing period')}</Text>
                </View>
                <View style={{ flex: 1.2 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{gatewayLabel(record.gatewayKey)}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 3 }} numberOfLines={1}>{record.providerDisplayName}</Text>
                </View>
                <View style={{ flex: 1.1 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900' }} {...getTestProps(`payment-history-row-amount-${index}`)}>{formatAmount(record.totalAmount, record.currency)}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: statusTone.border, backgroundColor: statusTone.bg }} {...getTestProps(`payment-history-row-status-${index}`)}>
                    <Text style={{ color: statusTone.text, fontSize: 11, fontWeight: '800' }}>{record.statusLabel}</Text>
                  </View>
                </View>
                <View style={{ flex: 1.1, alignItems: 'flex-start' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="eye-outline" size={15} color={colors.primary} />
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.ledger.open', 'Open')}</Text>
                  </View>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      ) : (
        <View style={{ padding: 12, gap: 10 }}>
          {records.map((record, index) => {
            const statusTone = getStatusTone(record.status, colors);
            return (
              <TouchableOpacity key={record.id} onPress={() => onOpenDetails(record)} accessibilityLabel={record.referenceId} style={{ borderRadius: 16, borderWidth: 1, borderColor: selectedIds.has(record.documentId) ? colors.text : colors.border, backgroundColor: selectedIds.has(record.documentId) ? colors.primarySoft : colors.bg, padding: 14, gap: 10 }} {...getTestProps(`payment-history-card-${index}`)}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }} numberOfLines={1}>{record.referenceId}</Text>
                    <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>{formatShortDate(record.createdAt)} · {record.planLabel}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: statusTone.border, backgroundColor: statusTone.bg }} {...getTestProps(`payment-history-card-status-${index}`)}>
                    <Text style={{ color: statusTone.text, fontSize: 11, fontWeight: '800' }}>{record.statusLabel}</Text>
                  </View>
                </View>

                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                  <View>
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.gateway', 'Gateway')}</Text>
                    <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800', marginTop: 4 }}>{gatewayLabel(record.gatewayKey)}</Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.ledger.columns.amount', 'Amount')}</Text>
                    <Text style={{ color: colors.text, fontSize: 16, fontWeight: '900', marginTop: 4 }}>{formatAmount(record.totalAmount, record.currency)}</Text>
                  </View>
                </View>

                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <TouchableOpacity onPress={() => onToggleSelect(record.documentId)} accessibilityLabel="checkmark button" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} {...getTestProps(`payment-history-card-select-${index}`)}>
                    <View style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: selectedIds.has(record.documentId) ? colors.text : colors.textMuted, backgroundColor: selectedIds.has(record.documentId) ? colors.text : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                      {selectedIds.has(record.documentId) && <Ionicons name="checkmark" size={12} color={colors.bg} />}
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.ledger.select', 'Select')}</Text>
                  </TouchableOpacity>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="eye-outline" size={15} color={colors.primary} />
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.ledger.openDetails', 'Open details')}</Text>
                  </View>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      )}
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
