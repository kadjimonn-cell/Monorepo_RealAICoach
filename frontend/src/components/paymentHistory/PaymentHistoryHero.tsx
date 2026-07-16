import React from 'react';
import { Platform, Text, TouchableOpacity, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentHistorySummary } from './types';
import { formatAmount, formatLongDate } from './utils';

type Props = {
  summary: PaymentHistorySummary;
  isWide: boolean;
  colors: any;
  tx: (key: string, fallback: string) => string;
  bundleExporting: boolean;
  onExportPdf: () => void;
  onExportCsv: () => void;
  onPrint: () => void;
  onDownloadBundle: () => void;
};

const actionButtonStyle = (colors: any) => ({
  flexDirection: 'row' as const,
  alignItems: 'center' as const,
  gap: 8,
  paddingHorizontal: 14,
  paddingVertical: 11,
  borderRadius: 10,
  borderWidth: 1,
  borderColor: (globalThis as any).__alphaColor(colors.primaryText, '26'),
  backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '10'),
  ...(Platform.OS === 'web' ? { transition: 'opacity 160ms ease, transform 160ms ease' } as any : {}),
});

export const PaymentHistoryHero = ({ summary, isWide, colors, tx, bundleExporting, onExportPdf, onExportCsv, onPrint, onDownloadBundle }: Props) => (
  <LinearGradient
    colors={[colors.text, colors.cardMuted || colors.primary, colors.primary]}
    start={{ x: 0, y: 0 }}
    end={{ x: 1, y: 1 }}
    style={{ borderRadius: 24, padding: isWide ? 28 : 18, borderWidth: 1, borderColor: colors.border }}
    {...getTestProps('payment-history-hero')}
  >
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
      <View style={{ flex: 1, minWidth: 220 }}>
        <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.1 }} {...getTestProps('payment-history-hero-eyebrow')}>
          {tx('paymentHistory.hero.eyebrow', 'Enterprise payment ledger')}
        </Text>
        <Text style={{ color: colors.primaryText, fontSize: isWide ? 34 : 28, fontWeight: '900', letterSpacing: -1.1, marginTop: 10 }} {...getTestProps('payment-history-title')}>
          {tx('paymentHistory.header.title', 'Payment History')}
        </Text>
        <Text style={{ color: colors.primaryText + 'D9', fontSize: 13, lineHeight: 20, marginTop: 8, maxWidth: 960 }} {...getTestProps('payment-history-hero-subtitle')}>
          {tx('paymentHistory.header.subtitle', 'Audit-ready billing history with platform receipts, invoices, tax visibility, bulk exports, and payment automation controls.')}
        </Text>
      </View>

      <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', alignItems: 'stretch' }}>
        <View style={{ paddingHorizontal: 14, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primaryText, '26'), backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '10'), minWidth: 148 }} {...getTestProps('payment-history-hero-total-pill')}>
          <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }}>
            {tx('paymentHistory.hero.totalPaid', 'Total paid')}
          </Text>
          <Text style={{ color: colors.primaryText, fontSize: 20, fontWeight: '900', marginTop: 4 }} {...getTestProps('payment-history-hero-total-value')}>
            {formatAmount(summary.totalPaid, 'USD')}
          </Text>
        </View>
        <View style={{ paddingHorizontal: 14, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primaryText, '26'), backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '10'), minWidth: 148 }} {...getTestProps('payment-history-hero-last-pill')}>
          <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.9 }}>
            {tx('paymentHistory.hero.lastPayment', 'Last paid record')}
          </Text>
          <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800', marginTop: 4 }} {...getTestProps('payment-history-hero-last-value')}>
            {summary.lastSuccessfulPayment ? formatAmount(summary.lastSuccessfulPayment.totalAmount, summary.lastSuccessfulPayment.currency) : tx('paymentHistory.hero.noPaidRecord', 'No paid record')}
          </Text>
          <Text style={{ color: colors.primaryText + 'CC', fontSize: 10, fontWeight: '600', marginTop: 4 }} {...getTestProps('payment-history-hero-last-date')}>
            {summary.lastSuccessfulPayment ? formatLongDate(summary.lastSuccessfulPayment.createdAt) : tx('paymentHistory.hero.awaitingActivity', 'Awaiting activity')}
          </Text>
        </View>
      </View>
    </View>

    <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
      <TouchableOpacity onPress={onExportPdf} style={actionButtonStyle(colors)} accessibilityLabel="Export full payment history PDF" {...getTestProps('payment-history-export-pdf-button')}>
        <Ionicons name="document-text-outline" size={16} color={colors.primaryText} />
        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.actions.fullPdf', 'Full ledger PDF')}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={onExportCsv} style={actionButtonStyle(colors)} accessibilityLabel="Export full payment history CSV" {...getTestProps('payment-history-export-csv-button')}>
        <Ionicons name="download-outline" size={16} color={colors.primaryText} />
        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.actions.fullCsv', 'Full ledger CSV')}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={onPrint} style={actionButtonStyle(colors)} accessibilityLabel="Open print view" {...getTestProps('payment-history-print-button')}>
        <Ionicons name="print-outline" size={16} color={colors.primaryText} />
        <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.actions.print', 'Print')}</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={onDownloadBundle} disabled={bundleExporting} style={{ ...actionButtonStyle(colors), opacity: bundleExporting ? 0.7 : 1, backgroundColor: colors.successSoft, borderColor: (globalThis as any).__alphaColor(colors.success, '55') }} accessibilityLabel="Download all receipts PDF and CSV bundle" {...getTestProps('payment-history-download-bundle-button')}>
        <Ionicons name="archive-outline" size={16} color={colors.successText} />
        <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>{bundleExporting ? tx('paymentHistory.actions.preparing', 'Preparing…') : tx('paymentHistory.actions.filteredBundle', 'PDF + CSV bundle')}</Text>
      </TouchableOpacity>
    </View>
  </LinearGradient>
);

/* i18n-probe t('i18n.auto.probe') */
