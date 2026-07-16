import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Linking,
  Platform,
  RefreshControl,
  ScrollView,
  Text,
  TouchableOpacity,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AppShell from '../AppShell';
import { FadeSlideIn, PaymentHistorySkeleton } from '../SkeletonLoaders';
import { SecurePaymentAssurancePanel } from '../payment/SecurePaymentAssurancePanel';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useTranslation } from '../../hooks/useTranslation';
import { getTestProps } from '../../utils/testProps';
import { PaymentHistoryDetailSheet } from '../paymentHistory/PaymentHistoryDetailSheet';
import { PaymentHistoryFilters } from '../paymentHistory/PaymentHistoryFilters';
import { PaymentHistoryHero } from '../paymentHistory/PaymentHistoryHero';
import { PaymentHistoryInsights } from '../paymentHistory/PaymentHistoryInsights';
import { PaymentHistoryLedger } from '../paymentHistory/PaymentHistoryLedger';
import { PaymentHistoryOperationsPanel } from '../paymentHistory/PaymentHistoryOperationsPanel';
import { PaymentHistoryRecord, PaymentReportPreferences, PaymentSortKey } from '../paymentHistory/types';
import {
  buildPaymentHistoryRecords,
  filterPaymentHistoryRecords,
  formatDateInputValue,
  sortPaymentHistoryRecords,
  summarizePaymentHistory,
} from '../paymentHistory/utils';

const PAYMENT_HISTORY_POLL_MS = 60000;

export default function PaymentHistoryV2() {
  const router = useRouter();
  const { user } = useAuth();
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width >= 1160;
  const isCompact = width < 760;
  const [payments, setPayments] = useState<any[]>([]);
  const [transactions, setTransactions] = useState<any[]>([]);
  const [availableGateways, setAvailableGateways] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [gatewayFilter, setGatewayFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [quickRange, setQuickRange] = useState('all');
  const [sortKey, setSortKey] = useState<PaymentSortKey>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkExporting, setBulkExporting] = useState(false);
  const [bulkAllExporting, setBulkAllExporting] = useState(false);
  const [bundleExporting, setBundleExporting] = useState(false);
  const [selectedYear, setSelectedYear] = useState(String(new Date().getFullYear() - 1));
  const [emailingYearly, setEmailingYearly] = useState(false);
  const [reportPrefs, setReportPrefs] = useState<PaymentReportPreferences | null>(null);
  const [sendingReport, setSendingReport] = useState(false);
  const [receiptTransparencyMode, setReceiptTransparencyMode] = useState(true);
  const [taxStatementScope, setTaxStatementScope] = useState<'monthly' | 'yearly'>('monthly');
  const [taxStatementYear, setTaxStatementYear] = useState(String(new Date().getFullYear()));
  const [taxStatementMonth, setTaxStatementMonth] = useState(String(new Date().getMonth() + 1));
  const [downloadingTaxStatement, setDownloadingTaxStatement] = useState<'csv' | 'pdf' | null>(null);
  const [emailingReceipt, setEmailingReceipt] = useState<string | null>(null);
  const [emailingInvoice, setEmailingInvoice] = useState<string | null>(null);
  const [detailRecord, setDetailRecord] = useState<PaymentHistoryRecord | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [actionNotice, setActionNotice] = useState('');
  const cachedTokenRef = useRef<string | null>(null);
  const envReactBase = typeof process !== 'undefined' ? (process.env?.['REACT_APP_BACKEND_URL'] || '') : '';
  const envExpoBase = typeof process !== 'undefined' ? (process.env?.['EXPO_PUBLIC_BACKEND_URL'] || '') : '';
  const backendBaseUrl = (envReactBase || envExpoBase || '').replace(/\/$/, '');

  useEffect(() => {
    AsyncStorage.getItem('session_token').then((token) => { cachedTokenRef.current = token; });
  }, []);

  const getWebToken = useCallback(() => {
    if (cachedTokenRef.current) return cachedTokenRef.current;
    if (typeof window !== 'undefined') {
      const token = window.localStorage.getItem('session_token');
      if (token) cachedTokenRef.current = token;
      return token;
    }
    return null;
  }, []);

  const palette = useMemo(() => ({
    ...colors,
    errorSoft: colors.error ? `${colors.error}12` : colors.bgSoft,
    surfaceRaised: darkMode ? colors.cardMuted : colors.bg,
  }), [colors, darkMode]);

  const fetchHistory = useCallback(async (refreshMode = false) => {
    try {
      if (!refreshMode) setLoading(true);
      const params: Record<string, string> = {};
      if (gatewayFilter !== 'all') params.gateway = gatewayFilter;
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      const response = await api.get('/payments/history', { params, skipDedupe: true });
      setPayments(response.data.payments || []);
      setTransactions(response.data.transactions || []);
      setAvailableGateways(response.data.available_gateways || []);
    } catch (error: any) {
      setActionNotice(error?.response?.data?.detail || tx('paymentHistory.errors.loadFailed', 'Unable to load payment history right now.'));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [endDate, gatewayFilter, startDate, tx]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (Platform.OS === 'web' && typeof document !== 'undefined' && document.hidden) {
        return;
      }
      void fetchHistory(true);
    }, PAYMENT_HISTORY_POLL_MS);
    return () => clearInterval(timer);
  }, [fetchHistory]);

  useEffect(() => {
    api.get('/payments/report-preferences').then((response) => setReportPrefs(response.data)).catch(() => {});
    api.get('/payments/receipt-transparency-mode')
      .then((response) => {
        if (typeof response?.data?.enabled === 'boolean') {
          setReceiptTransparencyMode(response.data.enabled);
        }
      })
      .catch(() => setReceiptTransparencyMode(true));
  }, []);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [gatewayFilter, startDate, endDate, searchText, statusFilter]);

  const historyRecords = useMemo(() => buildPaymentHistoryRecords(payments, transactions), [payments, transactions]);
  const filteredRecords = useMemo(() => {
    const searched = filterPaymentHistoryRecords(historyRecords, searchText, statusFilter);
    return sortPaymentHistoryRecords(searched, sortKey, sortDirection);
  }, [historyRecords, searchText, sortDirection, sortKey, statusFilter]);
  const summary = useMemo(() => summarizePaymentHistory(filteredRecords, user), [filteredRecords, user]);

  const onRefresh = () => {
    setRefreshing(true);
    void fetchHistory(true);
  };

  const setQuickRangeFromValue = (value: string) => {
    setQuickRange(value);
    if (value === 'all') {
      setStartDate('');
      setEndDate('');
      return;
    }
    const now = new Date();
    if (value === 'ytd') {
      setStartDate(`${now.getFullYear()}-01-01`);
      setEndDate(formatDateInputValue(now));
      return;
    }
    const days = value === '30d' ? 30 : 90;
    const nextStart = new Date(now.getTime() - days * 86400000);
    setStartDate(formatDateInputValue(nextStart));
    setEndDate(formatDateInputValue(now));
  };

  const handleStartDateChange = (value: string) => {
    setQuickRange('custom');
    setStartDate(value);
  };

  const handleEndDateChange = (value: string) => {
    setQuickRange('custom');
    setEndDate(value);
  };

  const clearFilters = () => {
    setSearchText('');
    setGatewayFilter('all');
    setStatusFilter('all');
    setStartDate('');
    setEndDate('');
    setQuickRange('all');
    setSortKey('date');
    setSortDirection('desc');
  };

  const toggleReportPref = async (key: 'weekly_enabled' | 'monthly_enabled' | 'renewal_reminders') => {
    if (!reportPrefs) return;
    const nextPrefs = { ...reportPrefs, [key]: !reportPrefs[key] };
    setReportPrefs(nextPrefs);
    try {
      await api.put('/payments/report-preferences', { [key]: nextPrefs[key] });
      setActionNotice(tx('paymentHistory.messages.reportPreferenceSaved', 'Report preference updated.'));
    } catch {
      setReportPrefs(reportPrefs);
      setActionNotice(tx('paymentHistory.errors.reportPreferenceFailed', 'Unable to update the report preference.'));
    }
  };

  const sendReportNow = async () => {
    setSendingReport(true);
    try {
      await api.post('/payments/send-report');
      setActionNotice(tx('paymentHistory.messages.reportSent', 'Payment summary email sent.'));
    } catch (error: any) {
      setActionNotice(error?.response?.data?.detail || tx('paymentHistory.errors.reportSendFailed', 'Unable to send the report right now.'));
    } finally {
      setSendingReport(false);
    }
  };

  const toggleReceiptTransparencyMode = async () => {
    const nextValue = !receiptTransparencyMode;
    setReceiptTransparencyMode(nextValue);
    try {
      await api.post('/payments/receipt-transparency-mode', { enabled: nextValue });
      setActionNotice(nextValue ? tx('paymentHistory.messages.transparencyEnabled', 'Receipt Transparency Mode enabled.') : tx('paymentHistory.messages.transparencyDisabled', 'Receipt Transparency Mode disabled.'));
    } catch {
      setReceiptTransparencyMode(!nextValue);
      setActionNotice(tx('paymentHistory.errors.transparencyFailed', 'Unable to update Receipt Transparency Mode.'));
    }
  };

  const downloadTaxStatement = async (format: 'csv' | 'pdf') => {
    setDownloadingTaxStatement(format);
    try {
      const params = new URLSearchParams({ scope: taxStatementScope, year: taxStatementYear });
      if (taxStatementScope === 'monthly') params.set('month', taxStatementMonth);

      if (Platform.OS === 'web') {
        const token = getWebToken();
        const response = await fetch(`${backendBaseUrl}/api/payments/tax-statement/${format}?${params.toString()}`, {
          method: 'GET',
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          credentials: 'include',
        });
        if (!response.ok) throw new Error(tx('paymentHistory.errors.taxStatementFailed', 'Unable to download the tax statement.'));
        const blob = await response.blob();
        const objectUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = objectUrl;
        anchor.download = `tax_statement_${taxStatementScope}_${taxStatementYear}${taxStatementScope === 'monthly' ? `_${taxStatementMonth.padStart(2, '0')}` : ''}.${format}`;
        anchor.style.display = 'none';
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
      }
      setActionNotice(format === 'pdf' ? tx('paymentHistory.messages.taxPdfReady', 'Tax statement PDF downloaded.') : tx('paymentHistory.messages.taxCsvReady', 'Tax statement CSV downloaded.'));
    } catch (error: any) {
      setActionNotice(error?.message || tx('paymentHistory.errors.taxStatementFailed', 'Unable to download the tax statement.'));
    } finally {
      setDownloadingTaxStatement(null);
    }
  };

  const openEmbeddedDocument = (paymentId: string, docType: 'invoice' | 'receipt', action: 'view' | 'download' = 'view') => {
    const tm = receiptTransparencyMode ? '1' : '0';
    router.push(`/payment-document-v2?paymentId=${encodeURIComponent(paymentId)}&docType=${docType}&action=${action}&tm=${tm}` as any);
  };

  const openEmbeddedExport = (mode: 'pdf' | 'csv' | 'print') => {
    router.push(`/payment-history-export-v2?mode=${mode}` as any);
  };

  const openDocument = async (paymentId: string, docType: 'invoice' | 'receipt') => {
    if (Platform.OS === 'web') {
      openEmbeddedDocument(paymentId, docType, 'view');
      return;
    }
    const token = cachedTokenRef.current || await AsyncStorage.getItem('session_token');
    if (token) cachedTokenRef.current = token;
    const tokenQuery = token ? `&t=${encodeURIComponent(token)}` : '';
    const d = docType === 'receipt' ? 'r' : 'i';
    const tm = receiptTransparencyMode ? '1' : '0';
    await Linking.openURL(`${backendBaseUrl}/api/r/f?d=${d}&p=${encodeURIComponent(paymentId)}&v=1&tm=${tm}&cb=${Date.now()}${tokenQuery}`);
  };

  const downloadPdf = async (paymentId: string, docType: 'invoice' | 'receipt') => {
    if (Platform.OS === 'web') {
      openEmbeddedDocument(paymentId, docType, 'download');
      return;
    }
    const token = cachedTokenRef.current || await AsyncStorage.getItem('session_token');
    if (token) cachedTokenRef.current = token;
    const tokenQuery = token ? `&t=${encodeURIComponent(token)}` : '';
    const d = docType === 'receipt' ? 'r' : 'i';
    const tm = receiptTransparencyMode ? '1' : '0';
    await Linking.openURL(`${backendBaseUrl}/api/r/f?d=${d}&p=${encodeURIComponent(paymentId)}&v=0&tm=${tm}&cb=${Date.now()}${tokenQuery}`);
  };

  const handleExportPDF = () => {
    setActionNotice('');
    if (Platform.OS === 'web') {
      openEmbeddedExport('pdf');
      return;
    }
    const token = cachedTokenRef.current;
    const tokenQuery = token ? `&t=${encodeURIComponent(token)}` : '';
    Linking.openURL(`${backendBaseUrl}/api/r/x?f=p${tokenQuery}`);
  };

  const handleExportCSV = () => {
    setActionNotice('');
    if (Platform.OS === 'web') {
      openEmbeddedExport('csv');
      return;
    }
    const token = cachedTokenRef.current;
    const tokenQuery = token ? `&t=${encodeURIComponent(token)}` : '';
    Linking.openURL(`${backendBaseUrl}/api/r/x?f=c${tokenQuery}`);
  };

  const handlePrint = () => {
    setActionNotice('');
    if (Platform.OS !== 'web') return;
    openEmbeddedExport('print');
  };

  const toggleSelect = (id: string) => {
    if (!id) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const eligibleIds = filteredRecords.filter((record) => record.documentId).map((record) => record.documentId);
    if (eligibleIds.length === 0) return;
    const allSelected = eligibleIds.every((id) => selectedIds.has(id));
    setSelectedIds(allSelected ? new Set() : new Set(eligibleIds));
  };

  const handleBulkExport = async (docType: 'receipt' | 'invoice') => {
    if (selectedIds.size === 0 || Platform.OS !== 'web') return;
    setBulkExporting(true);
    try {
      const token = getWebToken();
      const response = await fetch(`${backendBaseUrl}/api/payments/bulk-export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ payment_ids: Array.from(selectedIds), doc_type: docType }),
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || tx('paymentHistory.errors.bulkExportFailed', 'Bulk export failed.'));
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `${docType}s_export.zip`;
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
      setSelectedIds(new Set());
      setActionNotice(`${docType === 'receipt' ? tx('paymentHistory.messages.receiptsExported', 'Receipt') : tx('paymentHistory.messages.invoicesExported', 'Invoice')} ZIP ready.`);
    } catch (error: any) {
      setActionNotice(error?.message || tx('paymentHistory.errors.bulkExportFailed', 'Bulk export failed.'));
    } finally {
      setBulkExporting(false);
    }
  };

  const handleBulkAllExport = async (format: 'combined' | 'zip') => {
    if (Platform.OS !== 'web') return;
    setBulkAllExporting(true);
    try {
      const token = getWebToken();
      const params = new URLSearchParams({ format });
      if (token) params.set('token', token);
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      const response = await fetch(`${backendBaseUrl}/api/payments/receipts/bulk-all?${params.toString()}`);
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || tx('paymentHistory.errors.bulkAllFailed', 'Unable to generate the bulk receipt export.'));
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = format === 'combined' ? 'receipts_combined.pdf' : 'receipts_bundle.zip';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
      setActionNotice(format === 'combined' ? tx('paymentHistory.messages.bulkCombinedReady', 'Combined receipts PDF downloaded.') : tx('paymentHistory.messages.bulkZipReady', 'ZIP of individual receipts downloaded.'));
    } catch (error: any) {
      setActionNotice(error?.message || tx('paymentHistory.errors.bulkAllFailed', 'Unable to generate the bulk receipt export.'));
    } finally {
      setBulkAllExporting(false);
    }
  };

  const handleDownloadAllBundle = async () => {
    if (Platform.OS !== 'web') return;
    setBundleExporting(true);
    try {
      const token = getWebToken();
      const params = new URLSearchParams();
      if (token) params.set('token', token);
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      const response = await fetch(`${backendBaseUrl}/api/payments/receipts/download-all-bundle?${params.toString()}`);
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || tx('paymentHistory.errors.bundleFailed', 'Unable to prepare the PDF and CSV bundle.'));
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = 'payment_history_receipts_bundle.zip';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
      setActionNotice(tx('paymentHistory.messages.bundleReady', 'Combined PDF + CSV bundle downloaded.'));
    } catch (error: any) {
      setActionNotice(error?.message || tx('paymentHistory.errors.bundleFailed', 'Unable to prepare the PDF and CSV bundle.'));
    } finally {
      setBundleExporting(false);
    }
  };

  const handleEmailYearlySummary = async () => {
    if (Platform.OS !== 'web') return;
    setEmailingYearly(true);
    try {
      const token = getWebToken();
      const response = await fetch(`${backendBaseUrl}/api/payments/receipts/email-yearly-summary`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ year: Number(selectedYear) }),
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => '');
        throw new Error(detail || tx('paymentHistory.errors.yearlySummaryFailed', 'Unable to email the yearly summary.'));
      }
      const payload = await response.json();
      setActionNotice(`${tx('paymentHistory.messages.yearlySummarySent', 'Yearly summary sent to')} ${payload.email || user?.email || ''}.`);
    } catch (error: any) {
      setActionNotice(error?.message || tx('paymentHistory.errors.yearlySummaryFailed', 'Unable to email the yearly summary.'));
    } finally {
      setEmailingYearly(false);
    }
  };

  const emailReceipt = async (paymentId: string) => {
    setEmailingReceipt(paymentId);
    try {
      await api.post(`/payments/email-receipt/${paymentId}`);
      setActionNotice(tx('paymentHistory.messages.receiptEmailed', 'Receipt emailed successfully.'));
    } catch (error: any) {
      setActionNotice(error?.response?.data?.detail || tx('paymentHistory.errors.receiptEmailFailed', 'Unable to email the receipt.'));
    } finally {
      setEmailingReceipt(null);
    }
  };

  const emailInvoice = async (paymentId: string) => {
    setEmailingInvoice(paymentId);
    try {
      await api.post(`/payments/email-invoice/${paymentId}`);
      setActionNotice(tx('paymentHistory.messages.invoiceEmailed', 'Invoice emailed successfully.'));
    } catch (error: any) {
      setActionNotice(error?.response?.data?.detail || tx('paymentHistory.errors.invoiceEmailFailed', 'Unable to email the invoice.'));
    } finally {
      setEmailingInvoice(null);
    }
  };

  const exportRangeLabel = startDate || endDate
    ? `${tx('paymentHistory.operations.currentRange', 'Current export range')}: ${startDate || tx('paymentHistory.operations.rangeStartOpen', 'Open start')} → ${endDate || tx('paymentHistory.operations.rangeEndOpen', 'Today')}`
    : tx('paymentHistory.operations.currentRangeAll', 'Current export range: all visible dates from the active ledger query.');

  if (loading) {
    return <AppShell><PaymentHistorySkeleton /></AppShell>;
  }

  return (
    <AppShell>
      <FadeSlideIn>
        <SafeAreaView style={{ flex: 1, backgroundColor: palette.bg }} edges={['top']}>
          <ScrollView showsVerticalScrollIndicator={false} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={palette.primary} />} contentContainerStyle={{ paddingBottom: 44 }} {...getTestProps('payment-history-page-scroll')}>
            <View style={{ paddingHorizontal: isWide ? 32 : isCompact ? 12 : 16, paddingTop: 18, gap: 16 }}>
              <PaymentHistoryHero summary={summary} isWide={isWide} colors={palette} tx={tx} bundleExporting={bundleExporting} onExportPdf={handleExportPDF} onExportCsv={handleExportCSV} onPrint={handlePrint} onDownloadBundle={handleDownloadAllBundle} />

              {!!actionNotice && (
                <View style={{ backgroundColor: palette.bgSoft, borderWidth: 1, borderColor: palette.border, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }} {...getTestProps('payment-history-action-notice')}>
                  <Text style={{ color: palette.textMuted, fontSize: 12, flex: 1, lineHeight: 18 }} {...getTestProps('payment-history-action-notice-text')}>{actionNotice}</Text>
                  <TouchableOpacity onPress={() => setActionNotice('')} accessibilityLabel="close button" style={{ width: 26, height: 26, borderRadius: 999, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.card }} {...getTestProps('payment-history-action-notice-dismiss-button')}>
                    <Ionicons name="close" size={14} color={palette.textMuted} />
                  </TouchableOpacity>
                </View>
              )}

              <PaymentHistoryInsights summary={summary} colors={palette} tx={tx} />

              <PaymentHistoryFilters
                colors={palette}
                tx={tx}
                searchText={searchText}
                onChangeSearchText={setSearchText}
                gatewayFilter={gatewayFilter}
                onChangeGatewayFilter={setGatewayFilter}
                availableGateways={availableGateways.length > 0 ? availableGateways : Array.from(new Set(historyRecords.map((record) => record.gatewayKey).filter(Boolean)))}
                statusFilter={statusFilter}
                onChangeStatusFilter={setStatusFilter}
                startDate={startDate}
                endDate={endDate}
                onChangeStartDate={handleStartDateChange}
                onChangeEndDate={handleEndDateChange}
                quickRange={quickRange}
                onChangeQuickRange={setQuickRangeFromValue}
                sortKey={sortKey}
                onChangeSortKey={setSortKey}
                sortDirection={sortDirection}
                onToggleSortDirection={() => setSortDirection((current) => current === 'desc' ? 'asc' : 'desc')}
                onClearFilters={clearFilters}
              />

              <SecurePaymentAssurancePanel provider="all" context="billing" panelTestId="billing-secure-assurance-panel" />

              <PaymentHistoryOperationsPanel colors={palette} receiptTransparencyMode={receiptTransparencyMode} onToggleTransparencyMode={toggleReceiptTransparencyMode} taxStatementScope={taxStatementScope} onSetTaxStatementScope={setTaxStatementScope} taxStatementYear={taxStatementYear} onSetTaxStatementYear={setTaxStatementYear} taxStatementMonth={taxStatementMonth} onSetTaxStatementMonth={setTaxStatementMonth} onDownloadTaxStatement={downloadTaxStatement} downloadingTaxStatement={downloadingTaxStatement} reportPrefs={reportPrefs} onToggleReportPref={toggleReportPref} onSendReportNow={sendReportNow} sendingReport={sendingReport} onHandleBulkAllExport={handleBulkAllExport} bulkAllExporting={bulkAllExporting} selectedYear={selectedYear} onSetSelectedYear={setSelectedYear} onEmailYearlySummary={handleEmailYearlySummary} emailingYearly={emailingYearly} exportRangeLabel={exportRangeLabel} tx={tx} />

              {selectedIds.size > 0 && Platform.OS === 'web' && (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: 14, borderRadius: 16, backgroundColor: palette.primarySoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(palette.primary, '33') }} {...getTestProps('payment-history-bulk-action-bar')}>
                  <Ionicons name="archive-outline" size={16} color={palette.primary} />
                  <Text style={{ color: palette.primary, fontSize: 12, fontWeight: '900' }} {...getTestProps('payment-history-bulk-selection-count')}>{selectedIds.size} {tx('paymentHistory.bulk.selectedRecords', 'selected record(s)')}</Text>
                  <TouchableOpacity onPress={() => { void handleBulkExport('receipt'); }} accessibilityLabel="Payment history bulk download receipts button" disabled={bulkExporting} style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: palette.text, opacity: bulkExporting ? 0.72 : 1 }} {...getTestProps('payment-history-bulk-download-receipts-button')}>
                    <Text style={{ color: palette.bg, fontSize: 12, fontWeight: '800' }}>{bulkExporting ? tx('paymentHistory.bulk.exporting', 'Exporting…') : tx('paymentHistory.bulk.downloadReceipts', 'Receipts ZIP')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => { void handleBulkExport('invoice'); }} accessibilityLabel="Payment history bulk download invoices button" disabled={bulkExporting} style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: palette.bgSoft, borderWidth: 1, borderColor: palette.border, opacity: bulkExporting ? 0.72 : 1 }} {...getTestProps('payment-history-bulk-download-invoices-button')}>
                    <Text style={{ color: palette.text, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.bulk.downloadInvoices', 'Invoices ZIP')}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => setSelectedIds(new Set())} accessibilityLabel="Payment history bulk clear button" style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, backgroundColor: 'transparent' }} {...getTestProps('payment-history-bulk-clear-button')}>
                    <Text style={{ color: palette.textMuted, fontSize: 12, fontWeight: '800' }}>{tx('paymentHistory.bulk.clearSelection', 'Clear')}</Text>
                  </TouchableOpacity>
                </View>
              )}

              {filteredRecords.length === 0 ? (
                <View style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 56, paddingHorizontal: 24, borderRadius: 20, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card }} {...getTestProps('payment-history-empty-state')}>
                  <View style={{ width: 72, height: 72, borderRadius: 999, backgroundColor: palette.bgSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="receipt-outline" size={34} color={palette.textMuted} />
                  </View>
                  <Text style={{ color: palette.text, fontSize: 18, fontWeight: '900', marginTop: 18 }} {...getTestProps('payment-history-empty-title')}>{searchText || gatewayFilter !== 'all' || statusFilter !== 'all' || startDate || endDate ? tx('paymentHistory.empty.filteredTitle', 'No records match this view') : tx('paymentHistory.empty.defaultTitle', 'No payment history yet')}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 13, lineHeight: 20, textAlign: 'center', marginTop: 8, maxWidth: 560 }} {...getTestProps('payment-history-empty-description')}>{searchText || gatewayFilter !== 'all' || statusFilter !== 'all' || startDate || endDate ? tx('paymentHistory.empty.filteredDescription', 'Adjust the filters or clear the current search to restore the full ledger.') : tx('paymentHistory.empty.defaultDescription', 'Your platform payment history will appear here automatically after your first subscription or transaction event.')}</Text>
                  <TouchableOpacity onPress={() => router.push('/subscription/plans' as any)} accessibilityLabel="Payment history view plans button" style={{ marginTop: 18, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 12, backgroundColor: palette.text }} {...getTestProps('payment-history-view-plans-button')}>
                    <Text style={{ color: palette.bg, fontSize: 12, fontWeight: '900' }}>{tx('paymentHistory.empty.viewPlans', 'View plans')}</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <PaymentHistoryLedger colors={palette} tx={tx} records={filteredRecords} isWide={isWide} selectedIds={selectedIds} onToggleSelect={toggleSelect} onToggleSelectAll={toggleSelectAll} onOpenDetails={(record) => { setDetailRecord(record); setDetailVisible(true); }} />
              )}
            </View>
          </ScrollView>

          <PaymentHistoryDetailSheet visible={detailVisible} record={detailRecord} colors={palette} isWide={isWide} receiptTransparencyMode={receiptTransparencyMode} emailingReceipt={emailingReceipt} emailingInvoice={emailingInvoice} canAccessInvoice={Boolean(user?.is_admin || user?.full_access || (user?.subscription_plan && user.subscription_plan !== 'free'))} onClose={() => setDetailVisible(false)} onOpenDocument={openDocument} onDownloadPdf={downloadPdf} onEmailReceipt={emailReceipt} onEmailInvoice={emailInvoice} tx={tx} />
        </SafeAreaView>
      </FadeSlideIn>
    </AppShell>
  );
}
