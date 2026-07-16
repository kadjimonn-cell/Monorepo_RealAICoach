import React from 'react';
import { Modal, Pressable, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentHistoryRecord } from './types';
import { formatAmount, formatLongDate } from './utils';

type Props = {
  visible: boolean;
  record: PaymentHistoryRecord | null;
  colors: any;
  isWide: boolean;
  receiptTransparencyMode: boolean;
  emailingReceipt: string | null;
  emailingInvoice: string | null;
  canAccessInvoice: boolean;
  onClose: () => void;
  onOpenDocument: (paymentId: string, docType: 'invoice' | 'receipt') => void;
  onDownloadPdf: (paymentId: string, docType: 'invoice' | 'receipt') => void;
  onEmailReceipt: (paymentId: string) => void;
  onEmailInvoice: (paymentId: string) => void;
  tx: (key: string, fallback: string) => string;
};

const MetricRow = ({ label, value, testId, colors }: { label: string; value: string; testId: string; colors: any }) => (
  <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 8 }} {...getTestProps(testId)}>
    <Text style={{ color: colors.textMuted, fontSize: 12, fontWeight: '700', flex: 1 }}>{label}</Text>
    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', flex: 1, textAlign: 'right' }}>{value}</Text>
  </View>
);

const SheetAction = ({ label, icon, onPress, disabled, colors, testId }: { label: string; icon: keyof typeof Ionicons.glyphMap; onPress: () => void; disabled?: boolean; colors: any; testId: string; }) => (
  <TouchableOpacity onPress={onPress} disabled={disabled} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, minHeight: 44, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, opacity: disabled ? 0.45 : 1 }} {...getTestProps(testId)} accessibilityLabel="label">
    <Ionicons name={icon} size={16} color={colors.text} />
    <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{label}</Text>
  </TouchableOpacity>
);

export const PaymentHistoryDetailSheet = ({ visible, record, colors, isWide, receiptTransparencyMode, emailingReceipt, emailingInvoice, canAccessInvoice, onClose, onOpenDocument, onDownloadPdf, onEmailReceipt, onEmailInvoice, tx }: Props) => {
  const paidRecord = record?.isSuccessful ?? false;

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: 'rgba(15,23,42,0.54)', justifyContent: 'flex-end' }} onPress={onClose} {...getTestProps('payment-history-detail-overlay')} accessibilityLabel="Close">
        <Pressable onPress={(event) => event.stopPropagation?.()} accessibilityLabel="Payment history detail sheet button" style={{ width: isWide ? 460 : '100%', maxHeight: isWide ? '100%' : '84%', backgroundColor: colors.card, borderTopLeftRadius: isWide ? 0 : 24, borderTopRightRadius: isWide ? 0 : 24, borderLeftWidth: isWide ? 1 : 0, borderTopWidth: isWide ? 0 : 1, borderColor: colors.border, paddingTop: 18 }} {...getTestProps('payment-history-detail-sheet')}>
          <View style={{ paddingHorizontal: 18, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: colors.border, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }}>{tx('paymentHistory.detail.eyebrow', 'Payment detail panel')}</Text>
              <Text style={{ color: colors.text, fontSize: 18, fontWeight: '900', marginTop: 6 }} {...getTestProps('payment-history-detail-title')}>{record?.referenceId || tx('paymentHistory.detail.noRecord', 'No record selected')}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 6 }} {...getTestProps('payment-history-detail-subtitle')}>{record ? `${record.planLabel} · ${record.providerDisplayName} · ${formatLongDate(record.createdAt)}` : tx('paymentHistory.detail.placeholder', 'Select a row to inspect payment metadata.')}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={{ width: 34, height: 34, borderRadius: 999, backgroundColor: colors.bgSoft, alignItems: 'center', justifyContent: 'center' }} {...getTestProps('payment-history-detail-close-button')} accessibilityLabel="close button">
              <Ionicons name="close" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          </View>

          <ScrollView contentContainerStyle={{ paddingHorizontal: 18, paddingVertical: 16, gap: 16 }} showsVerticalScrollIndicator={false}>
            <View style={{ borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 16, gap: 10 }} {...getTestProps('payment-history-detail-overview-card')}>
              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }} {...getTestProps('payment-history-detail-status-chip')}><Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{record?.statusLabel || '—'}</Text></View>
                <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }} {...getTestProps('payment-history-detail-source-chip')}><Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{record?.sourceLabel || '—'}</Text></View>
                <View style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card }} {...getTestProps('payment-history-detail-transparency-chip')}><Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{receiptTransparencyMode ? tx('paymentHistory.detail.transparencyOn', 'Transparency ON') : tx('paymentHistory.detail.transparencyOff', 'Transparency OFF')}</Text></View>
              </View>

              <MetricRow label={tx('paymentHistory.detail.amountCharged', 'Amount charged')} value={record ? formatAmount(record.totalAmount, record.currency) : '—'} testId="payment-history-detail-amount-charged" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.subtotal', 'Subtotal / base amount')} value={record ? formatAmount(record.amount, record.currency) : '—'} testId="payment-history-detail-subtotal" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.taxAmount', 'Applicable tax')} value={record ? formatAmount(record.taxAmount, record.currency) : '—'} testId="payment-history-detail-tax-amount" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.processingFee', 'Payment processing fee')} value={record ? formatAmount(record.processingFee, record.currency) : '—'} testId="payment-history-detail-processing-fee" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.netSettlement', 'Net settlement after fee')} value={record ? formatAmount(record.amountNet, record.currency) : '—'} testId="payment-history-detail-net-settlement" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.gateway', 'Gateway')} value={record?.providerDisplayName || '—'} testId="payment-history-detail-gateway" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.billingPeriod', 'Billing period')} value={record?.billingPeriod || '—'} testId="payment-history-detail-billing-period" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.jurisdiction', 'Jurisdiction')} value={record?.jurisdictionLabel || '—'} testId="payment-history-detail-jurisdiction" colors={colors} />
              <MetricRow label={tx('paymentHistory.detail.taxRate', 'Tax rate')} value={record ? `${(record.taxRate * 100).toFixed(2)}%` : '—'} testId="payment-history-detail-tax-rate" colors={colors} />
            </View>

            {!!record && (
              <View style={{ gap: 10 }} {...getTestProps('payment-history-detail-actions-section')}>
                <Text style={{ color: colors.text, fontSize: 14, fontWeight: '900' }}>{tx('paymentHistory.detail.actionsTitle', 'Document actions')}</Text>
                <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                  <SheetAction label={tx('paymentHistory.detail.viewInvoice', 'View invoice')} icon="eye-outline" onPress={() => onOpenDocument(record.documentId, 'invoice')} disabled={!canAccessInvoice} colors={colors} testId="payment-history-detail-view-invoice-button" />
                  <SheetAction label={tx('paymentHistory.detail.downloadInvoice', 'Download invoice PDF')} icon="download-outline" onPress={() => onDownloadPdf(record.documentId, 'invoice')} disabled={!canAccessInvoice} colors={colors} testId="payment-history-detail-download-invoice-button" />
                  <SheetAction label={tx('paymentHistory.detail.emailInvoice', emailingInvoice === record.documentId ? 'Sending invoice…' : 'Email invoice')} icon={emailingInvoice === record.documentId ? 'hourglass-outline' : 'mail-outline'} onPress={() => onEmailInvoice(record.documentId)} disabled={!canAccessInvoice || emailingInvoice === record.documentId} colors={colors} testId="payment-history-detail-email-invoice-button" />
                </View>

                {!canAccessInvoice && (
                  <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 12 }} {...getTestProps('payment-history-detail-invoice-upgrade-notice')}>
                    <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, fontWeight: '700' }}>{tx('paymentHistory.detail.invoiceUpgradeNotice', 'Invoice documents require a Basic plan or higher. Upgrade to unlock invoice downloads.')}</Text>
                  </View>
                )}

                <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                  <SheetAction label={tx('paymentHistory.detail.viewReceipt', 'View receipt')} icon="receipt-outline" onPress={() => onOpenDocument(record.documentId, 'receipt')} disabled={!paidRecord} colors={colors} testId="payment-history-detail-view-receipt-button" />
                  <SheetAction label={tx('paymentHistory.detail.downloadReceipt', 'Download receipt PDF')} icon="document-attach-outline" onPress={() => onDownloadPdf(record.documentId, 'receipt')} disabled={!paidRecord} colors={colors} testId="payment-history-detail-download-receipt-button" />
                  <SheetAction label={tx('paymentHistory.detail.emailReceipt', emailingReceipt === record.documentId ? 'Sending receipt…' : 'Email receipt')} icon={emailingReceipt === record.documentId ? 'hourglass-outline' : 'mail-open-outline'} onPress={() => onEmailReceipt(record.documentId)} disabled={!paidRecord || emailingReceipt === record.documentId} colors={colors} testId="payment-history-detail-email-receipt-button" />
                </View>

                {!paidRecord && (
                  <View style={{ borderRadius: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '44'), backgroundColor: colors.warningSoft, padding: 12 }} {...getTestProps('payment-history-detail-receipt-warning')}>
                    <Text style={{ color: colors.warningText, fontSize: 12, lineHeight: 18, fontWeight: '700' }}>{tx('paymentHistory.detail.receiptPendingNotice', 'Receipt actions unlock once the payment status becomes Paid or Completed.')}</Text>
                  </View>
                )}
              </View>
            )}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
};
/* i18n-probe t('i18n.auto.probe') */
