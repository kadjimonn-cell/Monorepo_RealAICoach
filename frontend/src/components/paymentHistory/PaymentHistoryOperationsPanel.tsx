import React from 'react';
import { Platform, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { getTestProps } from '../../utils/testProps';
import { PaymentReportPreferences } from './types';

type Props = {
  colors: any;
  receiptTransparencyMode: boolean;
  onToggleTransparencyMode: () => void;
  taxStatementScope: 'monthly' | 'yearly';
  onSetTaxStatementScope: (value: 'monthly' | 'yearly') => void;
  taxStatementYear: string;
  onSetTaxStatementYear: (value: string) => void;
  taxStatementMonth: string;
  onSetTaxStatementMonth: (value: string) => void;
  onDownloadTaxStatement: (format: 'csv' | 'pdf') => void;
  downloadingTaxStatement: 'csv' | 'pdf' | null;
  reportPrefs: PaymentReportPreferences | null;
  onToggleReportPref: (key: 'weekly_enabled' | 'monthly_enabled' | 'renewal_reminders') => void;
  onSendReportNow: () => void;
  sendingReport: boolean;
  onHandleBulkAllExport: (format: 'combined' | 'zip') => void;
  bulkAllExporting: boolean;
  selectedYear: string;
  onSetSelectedYear: (value: string) => void;
  onEmailYearlySummary: () => void;
  emailingYearly: boolean;
  exportRangeLabel: string;
  tx: (key: string, fallback: string) => string;
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const renderYearField = (value: string, onChange: (value: string) => void, colors: any, testId: string) => {
  if (Platform.OS === 'web') {
    return React.createElement('input', {
      type: 'number',
      min: 2000,
      max: 2100,
      step: 1,
      value,
      onChange: (event: any) => onChange(event.target.value),
      ...getTestProps(testId),
      style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${colors.border}`, backgroundColor: colors.bg, color: colors.text, fontSize: 13, fontWeight: 700 },
    });
  }
  return <TextInput keyboardType="numeric" value={value} onChangeText={onChange} style={{ borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, color: colors.text, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontWeight: '700', fontSize: 13 }} {...getTestProps(testId)} />;
};

const ToggleRow = ({ label, description, active, onPress, icon, testId, colors }: { label: string; description: string; active: boolean; onPress: () => void; icon: keyof typeof Ionicons.glyphMap; testId: string; colors: any; }) => (
  <TouchableOpacity onPress={onPress} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }} {...getTestProps(testId)} accessibilityLabel="label">
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flex: 1 }}>
      <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={18} color={colors.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }}>{label}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 2 }}>{description}</Text>
      </View>
    </View>
    <View style={{ width: 48, height: 28, borderRadius: 999, backgroundColor: active ? colors.primary : colors.bgSoft, padding: 3, borderWidth: 1, borderColor: active ? colors.primary : colors.border, justifyContent: 'center' }}>
      <View style={{ width: 20, height: 20, borderRadius: 999, backgroundColor: colors.bg, alignSelf: active ? 'flex-end' : 'flex-start' }} />
    </View>
  </TouchableOpacity>
);

export const PaymentHistoryOperationsPanel = ({ colors, receiptTransparencyMode, onToggleTransparencyMode, taxStatementScope, onSetTaxStatementScope, taxStatementYear, onSetTaxStatementYear, taxStatementMonth, onSetTaxStatementMonth, onDownloadTaxStatement, downloadingTaxStatement, reportPrefs, onToggleReportPref, onSendReportNow, sendingReport, onHandleBulkAllExport, bulkAllExporting, selectedYear, onSetSelectedYear, onEmailYearlySummary, emailingYearly, exportRangeLabel, tx }: Props) => {
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 6 }, (_, index) => String(currentYear - index));

  return (
    <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
      <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.card, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 14 }} {...getTestProps('payment-history-compliance-card')}>
        <View>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('payment-history-compliance-title')}>{tx('paymentHistory.operations.complianceTitle', 'Compliance & document controls')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('paymentHistory.operations.complianceSubtitle', 'Use platform tax visibility, transparency, and statement generation without leaving the ledger.')}</Text>
        </View>

        <ToggleRow label={tx('paymentHistory.operations.transparency', 'Receipt Transparency Mode')} description={tx('paymentHistory.operations.transparencyDescription', 'Include tax basis, fee policy, and net settlement explanations on receipt flows.')} active={receiptTransparencyMode} onPress={onToggleTransparencyMode} icon="shield-checkmark-outline" testId="payment-history-transparency-toggle" colors={colors} />

        <View style={{ height: 1, backgroundColor: colors.border }} />

        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900' }} {...getTestProps('payment-history-tax-section-title')}>{tx('paymentHistory.operations.taxTitle', 'Tax statement export')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {(['monthly', 'yearly'] as const).map((scope) => (
            <TouchableOpacity key={scope} onPress={() => onSetTaxStatementScope(scope)} accessibilityLabel="On set tax statement scope in payment history operations panel" style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: taxStatementScope === scope ? colors.primary : colors.bgSoft, borderWidth: 1, borderColor: taxStatementScope === scope ? colors.primary : colors.border }} {...getTestProps(`payment-history-tax-scope-${scope}`)}>
              <Text style={{ color: taxStatementScope === scope ? (colors.primaryText || colors.text) : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{scope === 'monthly' ? tx('paymentHistory.operations.monthly', 'Monthly') : tx('paymentHistory.operations.yearly', 'Yearly')}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
          <View style={{ flex: 1, minWidth: 120, gap: 6 }}>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.operations.year', 'Year')}</Text>
            {renderYearField(taxStatementYear, onSetTaxStatementYear, colors, 'payment-history-tax-year-input')}
          </View>
          {taxStatementScope === 'monthly' && (
            <View style={{ flex: 1, minWidth: 140, gap: 6 }}>
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.8 }}>{tx('paymentHistory.operations.month', 'Month')}</Text>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                {MONTHS.map((month, index) => {
                  const value = String(index + 1);
                  return <TouchableOpacity key={month} onPress={() => onSetTaxStatementMonth(value)} accessibilityLabel="month" style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 10, backgroundColor: taxStatementMonth === value ? colors.primary : colors.bgSoft, borderWidth: 1, borderColor: taxStatementMonth === value ? colors.primary : colors.border }} {...getTestProps(`payment-history-tax-month-${value}`)}><Text style={{ color: taxStatementMonth === value ? (colors.primaryText || colors.text) : colors.textMuted, fontSize: 11, fontWeight: '800' }}>{month}</Text></TouchableOpacity>;
                })}
              </View>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TouchableOpacity onPress={() => onDownloadTaxStatement('pdf')} accessibilityLabel="document attach outline button" disabled={Boolean(downloadingTaxStatement)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: colors.primary, opacity: downloadingTaxStatement ? 0.72 : 1 }} {...getTestProps('payment-history-tax-download-pdf-button')}>
            <Ionicons name="document-attach-outline" size={16} color={colors.primaryText} />
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>{downloadingTaxStatement === 'pdf' ? tx('paymentHistory.operations.preparingPdf', 'Preparing PDF…') : tx('paymentHistory.operations.downloadPdf', 'Download PDF')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => onDownloadTaxStatement('csv')} accessibilityLabel="download outline button" disabled={Boolean(downloadingTaxStatement)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, opacity: downloadingTaxStatement ? 0.72 : 1 }} {...getTestProps('payment-history-tax-download-csv-button')}>
            <Ionicons name="download-outline" size={16} color={colors.text} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{downloadingTaxStatement === 'csv' ? tx('paymentHistory.operations.preparingCsv', 'Preparing CSV…') : tx('paymentHistory.operations.downloadCsv', 'Download CSV')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flex: 1, minWidth: 280, backgroundColor: colors.card, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 14 }} {...getTestProps('payment-history-automation-card')}>
        <View>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} {...getTestProps('payment-history-automation-title')}>{tx('paymentHistory.operations.automationTitle', 'Automation & bulk operations')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{tx('paymentHistory.operations.automationSubtitle', 'Manage emailed reports, bulk receipt delivery, and annual finance summaries using live platform settings.')}</Text>
        </View>

        {reportPrefs && (
          <View style={{ gap: 12 }}>
            <ToggleRow label={tx('paymentHistory.operations.weeklyReport', 'Weekly report')} description={tx('paymentHistory.operations.weeklyDescription', 'Every Monday at 8:30 AM UTC.')} active={reportPrefs.weekly_enabled} onPress={() => onToggleReportPref('weekly_enabled')} icon="calendar-outline" testId="payment-history-weekly-report-toggle" colors={colors} />
            <ToggleRow label={tx('paymentHistory.operations.monthlyReport', 'Monthly report')} description={tx('paymentHistory.operations.monthlyDescription', 'First day of each month at 8:30 AM UTC.')} active={reportPrefs.monthly_enabled} onPress={() => onToggleReportPref('monthly_enabled')} icon="stats-chart-outline" testId="payment-history-monthly-report-toggle" colors={colors} />
            <ToggleRow label={tx('paymentHistory.operations.renewalReminder', 'Renewal reminders')} description={tx('paymentHistory.operations.renewalDescription', 'Receive reminders 7 days and 1 day before expiry.')} active={reportPrefs.renewal_reminders} onPress={() => onToggleReportPref('renewal_reminders')} icon="alarm-outline" testId="payment-history-renewal-toggle" colors={colors} />
          </View>
        )}

        <TouchableOpacity onPress={onSendReportNow} disabled={sendingReport} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '33'), backgroundColor: colors.primarySoft, opacity: sendingReport ? 0.7 : 1 }} {...getTestProps('payment-history-send-report-now-button')} accessibilityLabel="Send Report Now">
          <Ionicons name={sendingReport ? 'hourglass-outline' : 'send-outline'} size={16} color={colors.primary} />
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{sendingReport ? tx('paymentHistory.operations.sendingReport', 'Sending report…') : tx('paymentHistory.operations.sendReportNow', 'Send report now')}</Text>
        </TouchableOpacity>

        <View style={{ height: 1, backgroundColor: colors.border }} />

        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900' }} {...getTestProps('payment-history-bulk-exports-title')}>{tx('paymentHistory.operations.bulkReceipts', 'Bulk receipt exports')}</Text>
        <Text style={{ color: colors.textMuted, fontSize: 11, lineHeight: 16 }} {...getTestProps('payment-history-bulk-range-label')}>{exportRangeLabel}</Text>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <TouchableOpacity onPress={() => onHandleBulkAllExport('combined')} accessibilityLabel="document outline button" disabled={bulkAllExporting} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: colors.primary, opacity: bulkAllExporting ? 0.72 : 1 }} {...getTestProps('payment-history-bulk-combined-pdf-button')}>
            <Ionicons name="document-outline" size={16} color={colors.primaryText || colors.text} />
            <Text style={{ color: colors.primaryText || colors.text, fontSize: 12, fontWeight: '800' }}>{bulkAllExporting ? tx('paymentHistory.operations.generating', 'Generating…') : tx('paymentHistory.operations.combinedPdf', 'Combined PDF')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => onHandleBulkAllExport('zip')} accessibilityLabel="archive outline button" disabled={bulkAllExporting} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: colors.bgSoft, borderWidth: 1, borderColor: colors.border, opacity: bulkAllExporting ? 0.72 : 1 }} {...getTestProps('payment-history-bulk-zip-button')}>
            <Ionicons name="archive-outline" size={16} color={colors.text} />
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.operations.individualZip', 'Individual ZIP')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ height: 1, backgroundColor: colors.border }} />

        <Text style={{ color: colors.text, fontSize: 13, fontWeight: '900' }} {...getTestProps('payment-history-yearly-summary-title')}>{tx('paymentHistory.operations.yearlySummary', 'Email yearly summary')}</Text>
        <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
          {yearOptions.map((year) => (
            <TouchableOpacity
              key={year}
              onPress={() => onSetSelectedYear(year)}
              accessibilityLabel="year"
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: selectedYear === year ? colors.primary : colors.bgSoft, borderWidth: 1, borderColor: selectedYear === year ? colors.primary : colors.border }}
              {...getTestProps(`payment-history-year-pill-${year}`)}
            >
              <Text style={{ color: selectedYear === year ? (colors.primaryText || colors.text) : colors.textMuted, fontSize: 12, fontWeight: '800' }}>{year}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity onPress={onEmailYearlySummary} disabled={emailingYearly} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 12, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '33'), opacity: emailingYearly ? 0.7 : 1 }} {...getTestProps('payment-history-email-yearly-summary-button')} accessibilityLabel="Email Yearly Summary">
          <Ionicons name={emailingYearly ? 'hourglass-outline' : 'mail-outline'} size={16} color={colors.successText} />
          <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '800' }}>{emailingYearly ? tx('paymentHistory.operations.sendingYearly', 'Sending…') : tx('paymentHistory.operations.emailYearlySummary', 'Email yearly summary')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

/* i18n-probe t('i18n.auto.probe') */
