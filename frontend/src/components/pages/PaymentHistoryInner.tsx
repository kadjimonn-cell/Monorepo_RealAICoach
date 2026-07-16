import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  ActivityIndicator, RefreshControl, Platform, Linking, TextInput,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import api from '../../services/api';
import AsyncStorage from '@react-native-async-storage/async-storage';
import AppShell from '../AppShell';
import { PaymentHistorySkeleton, FadeSlideIn } from '../SkeletonLoaders';
import { SecurePaymentAssurancePanel } from '../payment/SecurePaymentAssurancePanel';
import { getTestProps } from '../../utils/testProps';
import { useTranslation } from '../../hooks/useTranslation';
import PaymentHistoryV2 from './PaymentHistoryV2';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';

const STATIC_COLORS = {
  success: 'var(--app-success)', warning: 'var(--app-warning)', error: 'var(--app-error)', // @theme-ok brand/role/state identifier
  stripe: 'var(--app-primary)', paypal: 'var(--app-primary)', fedapay: 'var(--app-primary)', // @theme-ok brand/role/state identifier
};

type SearchMode = 'all' | 'days' | 'months' | 'years';

interface Payment {
  id: string; plan_id: string; amount: number; currency: string;
  payment_method: string; payment_id: string; status: string; created_at: string;
}
interface Transaction {
  session_id: string; plan_id: string; billing_period: string;
  amount: number; currency: string; payment_method: string;
  payment_status: string; created_at: string;
}

function LegacyPaymentHistoryScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const { colors, darkMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const [payments, setPayments] = useState<Payment[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('all');
  const [searchDays, setSearchDays] = useState('');
  const [searchMonth, setSearchMonth] = useState('');
  const [searchYear, setSearchYear] = useState('');
  const [reportPrefs, setReportPrefs] = useState<{ weekly_enabled: boolean; monthly_enabled: boolean; renewal_reminders: boolean } | null>(null);
  const [showReportSettings, setShowReportSettings] = useState(false);
  const [sendingReport, setSendingReport] = useState(false);
  const [receiptTransparencyMode, setReceiptTransparencyMode] = useState(true);
  const [taxStatementScope, setTaxStatementScope] = useState<'monthly' | 'yearly'>('monthly');
  const [taxStatementYear, setTaxStatementYear] = useState(String(new Date().getFullYear()));
  const [taxStatementMonth, setTaxStatementMonth] = useState(String(new Date().getMonth() + 1));
  const [downloadingTaxStatement, setDownloadingTaxStatement] = useState<'csv' | 'pdf' | null>(null);
  const [emailingReceipt, setEmailingReceipt] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkExporting, setBulkExporting] = useState(false);
  const [showBulkAll, setShowBulkAll] = useState(false);
  const [bulkAllExporting, setBulkAllExporting] = useState(false);
  const [bundleExporting, setBundleExporting] = useState(false);
  const [bulkAllStartDate, setBulkAllStartDate] = useState('');
  const [bulkAllEndDate, setBulkAllEndDate] = useState('');
  const [emailingYearly, setEmailingYearly] = useState(false);
  const [selectedYear, setSelectedYear] = useState(String(new Date().getFullYear() - 1));  // Pre-cache token so PDF actions are synchronous (preserves user gesture for popup/download)
  const [actionNotice, setActionNotice] = useState('');
  const cachedTokenRef = useRef<string | null>(null);
  const envReactBase = typeof process !== 'undefined' ? (process.env?.['REACT_APP_BACKEND_URL'] || '') : '';
  const envExpoBase = typeof process !== 'undefined' ? (process.env?.['EXPO_PUBLIC_BACKEND_URL'] || '') : '';
  const backendBaseUrl = (envReactBase || envExpoBase || '').replace(/\/$/, '');
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isEmbeddedPreview = Platform.OS === 'web' && typeof window !== 'undefined' && window.top !== window.self;
  const getWebToken = () => {
    if (cachedTokenRef.current) return cachedTokenRef.current;
    if (typeof window !== 'undefined') {
      const stored = window.localStorage.getItem('session_token');
      if (stored) cachedTokenRef.current = stored;
      return stored;
    }
    return null;
  };
  useEffect(() => {
    AsyncStorage.getItem('session_token').then(t => { cachedTokenRef.current = t; });
  }, []);

  const C = useMemo(() => ({
    ...STATIC_COLORS,
    ...colors,
    primary: colors.primary, bg: colors.bg, bgSoft: colors.bgSoft,
    card: colors.card, text: colors.text, textSec: colors.textSec || colors.textSecondary || colors.text,
    textMuted: colors.textMuted, border: colors.border,
  }), [colors]);
  const summarySurface = useMemo(() => ({
    successBg: colors.successSoft,
    successBorder: colors.success + '44',
    successText: colors.successText,
    successLabel: colors.successText,
    infoBg: colors.primarySoft,
    infoBorder: colors.primary + '44',
    infoText: colors.primary,
    infoLabel: colors.primary,
    warnBg: colors.warningSoft,
    warnBorder: colors.warning + '44',
    warnText: colors.warningText,
    warnLabel: colors.warningText,
    panelBg: colors.card,
    panelBorder: C.border,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [C.border, colors]);
  const enterpriseSurface = useMemo(() => ({
    heroStart: darkMode ? colors.primary : colors.primary,
    heroMid: darkMode ? colors.purple : colors.indigo,
    heroEnd: darkMode ? colors.info : colors.info,
    heroSubText: colors.primaryText + 'E0',
    heroMetaBg: colors.primaryText + '22',
    heroMetaBorder: colors.primaryText + '44',
    cardBorderStrong: colors.primary + '33',
    actionCardBg: colors.card,
    actionCardBorder: colors.border,
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [colors, darkMode]);

  const loadHistory = useCallback(async () => {
    try {
      const resp = await api.get('/payments/history');
      setPayments(resp.data.payments || []);
      setTransactions(resp.data.transactions || []);
    } catch (e) { console.error('Failed to load payment history:', e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { loadHistory(); }, [loadHistory]);
  const onRefresh = () => { setRefreshing(true); loadHistory(); };

  useEffect(() => {
    api.get('/payments/report-preferences').then(r => setReportPrefs(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    api.get('/payments/receipt-transparency-mode')
      .then(r => {
        const enabled = r?.data?.enabled;
        if (typeof enabled === 'boolean') setReceiptTransparencyMode(enabled);
      })
      .catch(() => {
        setReceiptTransparencyMode(true);
      });
  }, []);

  const toggleReportPref = async (key: 'weekly_enabled' | 'monthly_enabled' | 'renewal_reminders') => {
    if (!reportPrefs) return;
    const newVal = !reportPrefs[key];
    setReportPrefs({ ...reportPrefs, [key]: newVal });
    try { await api.put('/payments/report-preferences', { [key]: newVal }); }
    catch { setReportPrefs({ ...reportPrefs, [key]: !newVal }); }
  };

  const sendReportNow = async () => {
    setSendingReport(true);
    try { await api.post('/payments/send-report'); }
    catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/PaymentHistoryInner.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    finally { setSendingReport(false); }
  };

  const toggleReceiptTransparencyMode = async () => {
    const next = !receiptTransparencyMode;
    setReceiptTransparencyMode(next);
    try {
      await api.post('/payments/receipt-transparency-mode', { enabled: next });
      setActionNotice(`Receipt Transparency Mode ${next ? 'enabled' : 'disabled'}.`);
    } catch {
      setReceiptTransparencyMode(!next);
      setActionNotice('Failed to update Receipt Transparency Mode.');
    }
  };

  const downloadTaxStatement = async (format: 'csv' | 'pdf') => {
    setDownloadingTaxStatement(format);
    try {
      const params = new URLSearchParams({
        scope: taxStatementScope,
        year: taxStatementYear,
      });
      if (taxStatementScope === 'monthly') params.set('month', taxStatementMonth);

      if (Platform.OS === 'web') {
        const token = getWebToken();
        const endpoint = `${backendBaseUrl}/api/payments/tax-statement/${format}?${params.toString()}`;
        const resp = await fetch(endpoint, {
          method: 'GET',
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          credentials: 'include',
        });
        if (!resp.ok) throw new Error(`Failed to download ${format.toUpperCase()} tax statement`);
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `tax_statement_${taxStatementScope}_${taxStatementYear}${taxStatementScope === 'monthly' ? `_${taxStatementMonth.padStart(2, '0')}` : ''}.${format}`;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
        setActionNotice(`${format.toUpperCase()} tax statement downloaded.`);
      } else {
        setActionNotice('Tax statement download is available on web currently.');
      }
    } catch (e: any) {
      setActionNotice(e?.message || `Failed to download ${format.toUpperCase()} tax statement.`);
    } finally {
      setDownloadingTaxStatement(null);
    }
  };

  const emailReceipt = async (paymentId: string) => {
    setEmailingReceipt(paymentId);
    try { await api.post(`/payments/email-receipt/${paymentId}`); }
    catch (e) { console.error('Email receipt failed:', e); }
    finally { setEmailingReceipt(null); }
  };

  const [emailingInvoice, setEmailingInvoice] = useState<string | null>(null);
  const emailInvoice = async (paymentId: string) => {
    setEmailingInvoice(paymentId);
    try { await api.post(`/payments/email-invoice/${paymentId}`); }
    catch (e) { console.error('Email invoice failed:', e); }
    finally { setEmailingInvoice(null); }
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _openWebWindow = (url: string) => {
    if (typeof window === 'undefined') return;
    window.location.assign(url);
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _triggerWebDownload = (url: string) => {
    if (typeof document === 'undefined') return;
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = '';
    anchor.rel = 'noopener noreferrer';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _buildWebTokenQuery = () => {
    const token = getWebToken();
    return token ? `&t=${encodeURIComponent(token)}` : '';
  };

  const openEmbeddedDocument = (paymentId: string, docType: 'invoice' | 'receipt', action: 'view' | 'download' = 'view') => {
    const tm = receiptTransparencyMode ? '1' : '0';
    router.push(`/payment-document-v2?paymentId=${encodeURIComponent(paymentId)}&docType=${docType}&action=${action}&tm=${tm}` as any);
  };

  const openEmbeddedExport = (mode: 'pdf' | 'csv' | 'print') => {
    router.push(`/payment-history-export-v2?mode=${mode}` as any);
  };

  const webClickProps = (handler: () => void) => (
    Platform.OS === 'web' ? ({ onClick: handler } as any) : {}
  );

  const getFilenameFromResponse = (response: Response, fallback: string) => {
    const disposition = response.headers.get('content-disposition') || '';
    const match = disposition.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i);
    if (!match?.[1]) return fallback;
    return decodeURIComponent(match[1].replace(/"/g, '').trim());
  };

  const fetchWebFile = async (path: string, fields: Record<string, string>, fallbackName: string) => {
    const token = getWebToken();
    const response = await fetch(`${backendBaseUrl}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/pdf,text/csv,application/octet-stream,*/*',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      credentials: 'include',
      body: JSON.stringify({ ...fields, t: token || '' }),
    });

    if (!response.ok) {
      const detail = await response.text().catch(() => '');
      throw new Error(`File request failed (${response.status}): ${detail || 'Unknown error'}`);
    }

    const blob = await response.blob();
    return {
      blob,
      filename: getFilenameFromResponse(response, fallbackName),
    };
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _downloadWebFile = async (path: string, fields: Record<string, string>, fallbackName: string) => {
    const { blob, filename } = await fetchWebFile(path, fields, fallbackName);
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.rel = 'noopener';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
  };

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const completedIds = filteredItems
      .filter(item => item.type === 'payment' && ['completed', 'paid'].includes(item.data.status))
      .map(item => item.data.id || item.data.payment_id);
    if (selectedIds.size === completedIds.length && completedIds.every(id => selectedIds.has(id))) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(completedIds));
    }
  };

  const handleBulkExport = async (docType: 'receipt' | 'invoice') => {
    if (selectedIds.size === 0 || Platform.OS !== 'web') return;
    setBulkExporting(true);
    try {
      const token = getWebToken();
      const resp = await fetch(`${backendBaseUrl}/api/payments/bulk-export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ payment_ids: Array.from(selectedIds), doc_type: docType }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Export failed');
      }
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${docType}s_export.zip`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
      setActionNotice(`ZIP with ${selectedIds.size} ${docType}(s) downloaded.`);
      setSelectedIds(new Set());
    } catch (e: any) {
      setActionNotice(e.message || 'Bulk export failed.');
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
      if (bulkAllStartDate) params.set('start_date', bulkAllStartDate);
      if (bulkAllEndDate) params.set('end_date', bulkAllEndDate);
      const resp = await fetch(`${backendBaseUrl}/api/payments/receipts/bulk-all?${params.toString()}`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Export failed');
      }
      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const dateSuffix = bulkAllStartDate || bulkAllEndDate ? `_${bulkAllStartDate || 'all'}_to_${bulkAllEndDate || 'now'}` : '';
      a.download = format === 'combined' ? `all_receipts${dateSuffix}.pdf` : `all_receipts${dateSuffix}.zip`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
      const count = resp.headers.get('X-Included-Count') || '?';
      setActionNotice(`${format === 'combined' ? 'Combined PDF' : 'ZIP'} with ${count} receipt(s) downloaded.`);
    } catch (e: any) {
      setActionNotice(e.message || 'Bulk all export failed.');
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
      if (bulkAllStartDate) params.set('start_date', bulkAllStartDate);
      if (bulkAllEndDate) params.set('end_date', bulkAllEndDate);

      const resp = await fetch(`${backendBaseUrl}/api/payments/receipts/download-all-bundle?${params.toString()}`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Download all bundle failed');
      }

      const blob = await resp.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const dateSuffix = bulkAllStartDate || bulkAllEndDate ? `_${bulkAllStartDate || 'all'}_to_${bulkAllEndDate || 'now'}` : '';
      a.download = `all_receipts_pdf_csv${dateSuffix}.zip`;
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);

      const count = resp.headers.get('X-Included-Count') || '?';
      setActionNotice(`Download All bundle ready: combined PDF + CSV (${count} receipts).`);
    } catch (e: any) {
      setActionNotice(e.message || 'Download all bundle failed.');
    } finally {
      setBundleExporting(false);
    }
  };

  const handleEmailYearlySummary = async () => {
    if (Platform.OS !== 'web') return;
    setEmailingYearly(true);
    try {
      const token = getWebToken();
      const resp = await fetch(`${backendBaseUrl}/api/payments/receipts/email-yearly-summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ year: parseInt(selectedYear, 10) }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to send email');
      }
      const data = await resp.json();
      setActionNotice(`Annual receipt summary for ${selectedYear} sent to ${data.email} (${data.receipts_count} receipts, $${data.total_amount}).`);
    } catch (e: any) {
      setActionNotice(e.message || 'Failed to email yearly summary.');
    } finally {
      setEmailingYearly(false);
    }
  };

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _openWebPdf = (path: string, fields: Record<string, string>, fallbackName: string, title: string) => {
    const token = getWebToken();
    const params = new URLSearchParams({ ...fields, v: '1', tm: receiptTransparencyMode ? '1' : '0', cb: String(Date.now()) });
    if (token) params.set('t', token);
    const url = `${backendBaseUrl}${path}?${params.toString()}`;
    window.open(url, '_blank', 'noopener');
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
    const url = `${backendBaseUrl}/api/r/f?d=${d}&p=${encodeURIComponent(paymentId)}&v=1&tm=${tm}&cb=${Date.now()}${tokenQuery}`;
    await Linking.openURL(url);
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
    const url = `${backendBaseUrl}/api/r/f?d=${d}&p=${encodeURIComponent(paymentId)}&v=0&tm=${tm}&cb=${Date.now()}${tokenQuery}`;
    await Linking.openURL(url);
  };

  const formatDate = (ds: string) => {
    try { return new Date(ds).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }); }
    catch { return ds; }
  };
  const formatTime = (ds: string) => {
    try { return new Date(ds).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }); }
    catch { return ''; }
  };
  const getMethodIcon = (m: string): any => m === 'stripe' ? 'card' : m === 'paypal' ? 'logo-paypal' : m === 'fedapay' ? 'phone-portrait' : 'cash';
  const getMethodColor = (m: string) => m === 'stripe' ? C.stripe : m === 'paypal' ? C.paypal : m === 'fedapay' ? C.fedapay : m?.includes('mobile_money') || m?.includes('kkiapay') ? C.fedapay : m?.includes('stripe') ? C.stripe : C.primary;
  const getMethodLabel = (m: string) => m === 'stripe' ? 'Stripe' : m === 'paypal' ? 'PayPal' : m === 'fedapay' ? 'FedaPay' : m?.includes('kkiapay') ? 'FedaPay' : m?.includes('mobile_money') ? 'FedaPay' : m?.includes('stripe') ? 'Stripe' : m || 'Stripe';
  const getStatusColor = (s: string) => s === 'completed' || s === 'paid' ? C.success : s === 'initiated' || s === 'pending' ? C.warning : C.error;
  const getStatusLabel = (s: string) => s === 'completed' || s === 'paid' ? 'Paid' : s === 'initiated' ? 'Pending' : s || 'Unknown';
  const getPlanName = (id: string) => ({ basic: 'Basic', premium: 'Premium', free: 'Free' }[id] || id);

  const CURRENCY_SYMBOLS: Record<string, string> = {
    USD: '$', EUR: '\u20ac', GBP: '\u00a3', JPY: '\u00a5', CAD: 'CA$', AUD: 'A$',
    INR: '\u20b9', BRL: 'R$', NGN: '\u20a6', KES: 'KSh', GHS: 'GH\u20b5', ZAR: 'R',
    XOF: 'CFA ', XAF: 'CFA ', CHF: 'CHF ', SEK: 'kr', PLN: 'z\u0142', TRY: '\u20ba',
    THB: '\u0e3f', RUB: '\u20bd', MXN: 'MX$', KRW: '\u20a9',
  };
  const NO_DECIMAL_CURRENCIES = ['JPY', 'KRW', 'XOF', 'XAF'];
  const formatAmount = (amount: number, currency?: string) => {
    const code = (currency || 'usd').toUpperCase();
    const sym = CURRENCY_SYMBOLS[code] || `${code} `;
    if (NO_DECIMAL_CURRENCIES.includes(code)) return `${sym}${Math.round(amount).toLocaleString()}`;
    return `${sym}${amount.toFixed(2)}`;
  };

  // Merge + deduplicate
  const allItems = useMemo(() => {
    const items: { type: 'payment' | 'transaction'; data: any; date: string }[] = [];
    payments.forEach(p => items.push({ type: 'payment', data: p, date: p.created_at }));
    transactions.forEach(t => items.push({ type: 'transaction', data: t, date: t.created_at }));
    items.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    const seen = new Set<string>();
    return items.filter(item => {
      const key = `${item.data.plan_id}-${item.data.amount}-${item.date?.slice(0, 16)}`;
      if (item.type === 'payment') { seen.add(key); return true; }
      return !seen.has(key);
    });
  }, [payments, transactions]);

  // Search/filter
  const filteredItems = useMemo(() => {
    if (searchMode === 'all') return allItems;
    const now = new Date();
    return allItems.filter(item => {
      const d = new Date(item.date);
      if (searchMode === 'days') {
        const days = parseInt(searchDays) || 0;
        if (days <= 0) return true;
        const cutoff = new Date(now.getTime() - days * 86400000);
        return d >= cutoff;
      }
      if (searchMode === 'months') {
        const m = parseInt(searchMonth) || 0;
        const y = parseInt(searchYear) || now.getFullYear();
        if (m > 0) return d.getMonth() + 1 === m && d.getFullYear() === y;
        return d.getFullYear() === y;
      }
      if (searchMode === 'years') {
        const y = parseInt(searchYear) || 0;
        if (y <= 0) return true;
        return d.getFullYear() === y;
      }
      return true;
    });
  }, [allItems, searchMode, searchDays, searchMonth, searchYear]);

  // Auto-refresh: poll every 30s for real-time data
  useEffect(() => {
    const _autoRefresh = setInterval(() => { try { loadHistory(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/pages/PaymentHistoryInner.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } }, 30000);
    return () => clearInterval(_autoRefresh);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const totalSpent = useMemo(() =>
    payments.filter(p => p.status === 'completed').reduce((sum, p) => sum + Number(p.total_amount ?? p.amount_gross ?? p.amount ?? 0), 0),
    [payments]
  );
  const filteredTotal = useMemo(() =>
    filteredItems.reduce((sum, item) => sum + Number(item.data.total_amount ?? item.data.amount_gross ?? item.data.amount ?? 0), 0),
    [filteredItems]
  );

  // ── Helpers for document viewing ──

  // Export PDF
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

  // Export CSV
  const handleExport = () => {
    setActionNotice('');
    if (Platform.OS === 'web') {
      openEmbeddedExport('csv');
      return;
    }
    const token = cachedTokenRef.current;
    const tokenQuery = token ? `&t=${encodeURIComponent(token)}` : '';
    Linking.openURL(`${backendBaseUrl}/api/r/x?f=c${tokenQuery}`);
  };

  // Print — navigates to print helper page
  const handlePrint = () => {
    setActionNotice('');
    if (Platform.OS !== 'web') return;
    openEmbeddedExport('print');
  };

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: 5 }, (_, i) => currentYear - i);
  const historyTitle = t('paymentHistory.header.title');

  if (loading) return (
    <AppShell><PaymentHistorySkeleton /></AppShell>
  );

  return (
    <AppShell>
      <FadeSlideIn>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        <ScrollView
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={C.primary} />}
          contentContainerStyle={{ paddingBottom: 40 }}
        >
          {/* Header */}
          <View style={{ paddingHorizontal: isWide ? 32 : 16, paddingTop: 16, paddingBottom: 8 }}>
            <LinearGradient
              colors={[enterpriseSurface.heroStart, enterpriseSurface.heroMid, enterpriseSurface.heroEnd]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={{ borderRadius: 24, padding: isWide ? 24 : 18, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder }}
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 180 }}>
                  <Text style={{ fontSize: isWide ? 32 : 24, fontWeight: '900', color: colors.text, letterSpacing: -0.8 }} testID="payment-history-title">{historyTitle === 'paymentHistory.header.title' ? 'Payment History' : historyTitle}</Text>
                  <Text style={{ fontSize: 13, color: enterpriseSurface.heroSubText, marginTop: 4, lineHeight: 20 }} data-testid="payment-history-hero-subtitle" testID="payment-history-hero-subtitle">{tx('paymentHistory.header.subtitle', 'Enterprise billing records, receipts, invoices, and exports in one secure workspace.')}</Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                  <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder, backgroundColor: enterpriseSurface.heroMetaBg }} data-testid="payment-history-hero-total-pill" testID="payment-history-hero-total-pill">
                    <Text style={{ color: enterpriseSurface.heroSubText, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('paymentHistory.header.totalPaid', 'Total You Paid')}</Text>
                    <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>${totalSpent.toFixed(2)}</Text>
                  </View>
                  <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder, backgroundColor: enterpriseSurface.heroMetaBg }} data-testid="payment-history-hero-count-pill" testID="payment-history-hero-count-pill">
                    <Text style={{ color: enterpriseSurface.heroSubText, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('paymentHistory.header.transactions', 'Transactions')}</Text>
                    <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{allItems.length}</Text>
                  </View>
                </View>
              </View>

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 16, position: 'relative', zIndex: 20 }}>
                <TouchableOpacity
                  accessibilityLabel="Export payment history as PDF"
                  onPress={handleExportPDF}
                  {...webClickProps(handleExportPDF)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 12, backgroundColor: enterpriseSurface.heroMetaBg, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder }}
                  data-testid="payment-history-hero-export-pdf" testID="payment-history-hero-export-pdf"
                  {...getTestProps('payment-export-pdf-btn')}
                >
                  <Ionicons name="document-text-outline" size={15} color={C.primaryText} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>{tx('paymentHistory.actions.exportPdf', 'Export PDF')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  accessibilityLabel="Export payment history as CSV"
                  onPress={handleExport}
                  {...webClickProps(handleExport)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 12, backgroundColor: enterpriseSurface.heroMetaBg, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder }}
                  data-testid="payment-history-hero-export-csv" testID="payment-history-hero-export-csv"
                  {...getTestProps('payment-export-btn')}
                >
                  <Ionicons name="download-outline" size={15} color={C.primaryText} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>{tx('paymentHistory.actions.exportCsv', 'Export CSV')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  accessibilityLabel="Print payment history"
                  onPress={handlePrint}
                  {...webClickProps(handlePrint)}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 12, backgroundColor: colors.overlay, borderWidth: 1, borderColor: enterpriseSurface.heroMetaBorder }}
                  data-testid="payment-history-hero-print" testID="payment-history-hero-print"
                  {...getTestProps('payment-print-btn')}
                >
                  <Ionicons name="print-outline" size={15} color={C.primaryText} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: colors.text }}>{tx('paymentHistory.actions.print', 'Print')}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  accessibilityLabel="Download all payment history in PDF and CSV"
                  onPress={handleDownloadAllBundle}
                  {...webClickProps(handleDownloadAllBundle)}
                  disabled={bundleExporting}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 11, borderRadius: 12, backgroundColor: colors.successSoft, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '80'), opacity: bundleExporting ? 0.7 : 1 }}
                  data-testid="payment-history-hero-download-all-pdf-csv" testID="payment-history-hero-download-all-pdf-csv"
                  {...getTestProps('payment-history-hero-download-all-pdf-csv')}
                >
                  <Ionicons name="archive-outline" size={15} color={colors.successText} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: colors.successText }}>{bundleExporting ? 'Preparing...' : 'Download All (PDF+CSV)'}</Text>
                </TouchableOpacity>
              </View>
            </LinearGradient>

          {!!actionNotice && (
            <View style={{ marginHorizontal: isWide ? 32 : 16, marginTop: 8, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }} {...getTestProps('payment-history-action-notice')}>
              <Text style={{ color: C.textMuted, fontSize: 12, flex: 1 }}>{actionNotice}</Text>
              <TouchableOpacity
                accessibilityLabel="Dismiss notice"
                onPress={() => setActionNotice('')}
                {...webClickProps(() => setActionNotice(''))}
                style={{ width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }}
                {...getTestProps('payment-history-action-notice-dismiss')}
              >
                <Ionicons name="close" size={14} color={C.textMuted} />
              </TouchableOpacity>
            </View>
          )}
          </View>

          {/* Receipt Transparency + Tax Statement */}
          <View style={{ paddingHorizontal: isWide ? 32 : 16, marginTop: 6, marginBottom: 10 }}>
            <SecurePaymentAssurancePanel
              provider="all"
              context="billing"
              panelTestId="billing-secure-assurance-panel"
            />
            <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: C.border }} data-testid="payment-history-tax-tools-card" testID="payment-history-tax-tools-card">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <View style={{ flex: 1, minWidth: 190 }}>
                  <Text style={{ fontSize: 14, fontWeight: '800', color: C.text }} data-testid="receipt-transparency-title" testID="receipt-transparency-title">Receipt Transparency Mode</Text>
                  <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 3 }} data-testid="receipt-transparency-description" testID="receipt-transparency-description">
                    Explain tax basis, fee policy, and net payout before every receipt download.
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={toggleReceiptTransparencyMode}
                  style={{ width: 54, height: 30, borderRadius: 999, backgroundColor: receiptTransparencyMode ? C.primary : C.bgSoft, justifyContent: 'center', padding: 3, borderWidth: 1, borderColor: receiptTransparencyMode ? C.primary : C.border }}
                  data-testid="receipt-transparency-toggle" testID="receipt-transparency-toggle"
                >
                  <View style={{ width: 22, height: 22, borderRadius: 999, backgroundColor: C.primaryText, alignSelf: receiptTransparencyMode ? 'flex-end' : 'flex-start' }} />
                </TouchableOpacity>
              </View>

              <View style={{ height: 1, backgroundColor: C.border, marginVertical: 14 }} />

              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }} data-testid="tax-statement-section-title" testID="tax-statement-section-title">Download Tax Statement</Text>
              <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 3, marginBottom: 10 }} data-testid="tax-statement-section-description" testID="tax-statement-section-description">
                Monthly or yearly tax statement with subtotal/tax/fees/gross/net and jurisdiction details.
              </Text>

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                {(['monthly', 'yearly'] as const).map(scope => (
                  <TouchableOpacity
                    key={scope}
                    onPress={() => setTaxStatementScope(scope)}
                    style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: taxStatementScope === scope ? C.primary : C.border, backgroundColor: taxStatementScope === scope ? C.primary : C.bgSoft }}
                    data-testid={`tax-statement-scope-${scope}`} testID={`tax-statement-scope-${scope}`}
                  >
                    <Text style={{ fontSize: 12, fontWeight: '700', color: taxStatementScope === scope ? C.primaryText : C.textMuted }}>{scope === 'monthly' ? 'Monthly' : 'Yearly'}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
                <View style={{ minWidth: 120 }}>
                  <Text style={{ fontSize: 10, color: C.textMuted, marginBottom: 4, fontWeight: '600' }}>Year</Text>
                  {React.createElement('select', {
                    value: taxStatementYear,
                    onChange: (e: any) => setTaxStatementYear(e.target.value),
                    'data-testid': 'tax-statement-year-select',
                    style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: C.bgSoft, color: C.text, fontSize: 12, fontWeight: 600 },
                  }, ...yearOptions.map(y => React.createElement('option', { key: y, value: String(y) }, String(y))))}
                </View>
                {taxStatementScope === 'monthly' && (
                  <View style={{ minWidth: 140 }}>
                    <Text style={{ fontSize: 10, color: C.textMuted, marginBottom: 4, fontWeight: '600' }}>Month</Text>
                    {React.createElement('select', {
                      value: taxStatementMonth,
                      onChange: (e: any) => setTaxStatementMonth(e.target.value),
                      'data-testid': 'tax-statement-month-select',
                      style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: C.bgSoft, color: C.text, fontSize: 12, fontWeight: 600 },
                    }, ...MONTHS.map((m, i) => React.createElement('option', { key: i + 1, value: String(i + 1) }, m)))}
                  </View>
                )}
              </View>

              <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
                <TouchableOpacity
                  onPress={() => { void downloadTaxStatement('pdf'); }}
                  disabled={!!downloadingTaxStatement}
                  style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.indigo, opacity: downloadingTaxStatement ? 0.7 : 1 }}
                  data-testid="tax-statement-download-pdf" testID="tax-statement-download-pdf"
                >
                  <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>{downloadingTaxStatement === 'pdf' ? 'Preparing PDF...' : 'Download PDF'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => { void downloadTaxStatement('csv'); }}
                  disabled={!!downloadingTaxStatement}
                  style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.info, opacity: downloadingTaxStatement ? 0.7 : 1 }}
                  data-testid="tax-statement-download-csv" testID="tax-statement-download-csv"
                >
                  <Text style={{ color: C.primaryText, fontSize: 12, fontWeight: '800' }}>{downloadingTaxStatement === 'csv' ? 'Preparing CSV...' : 'Download CSV'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>

          {/* Download All Receipts */}
          {Platform.OS === 'web' && allItems.length > 0 && (
            <View style={{ paddingHorizontal: isWide ? 32 : 16, marginTop: 12 }}>
              <TouchableOpacity
                onPress={() => setShowBulkAll(!showBulkAll)}
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.card, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: showBulkAll ? (globalThis as any).__alphaColor(C.primary, '50') : C.border }}
                data-testid="bulk-all-receipts-toggle" testID="bulk-all-receipts-toggle"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                  <View style={{ width: 40, height: 40, borderRadius: 12, backgroundColor: colors.purpleSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name="cloud-download-outline" size={20} color={colors.purpleText} />
                  </View>
                  <View>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>Download All Receipts</Text>
                    <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>Combined PDF or individual ZIP — with optional date filter</Text>
                  </View>
                </View>
                <Ionicons name={showBulkAll ? 'chevron-up' : 'chevron-down'} size={18} color={C.textMuted} />
              </TouchableOpacity>
              {showBulkAll && (
                <View style={{ backgroundColor: C.card, borderRadius: 16, padding: 18, marginTop: 8, borderWidth: 1, borderColor: C.border }} data-testid="bulk-all-receipts-panel" testID="bulk-all-receipts-panel">
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 12 }}>Date Range (Optional)</Text>
                  <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
                    <View style={{ flex: 1, minWidth: 150 }}>
                      <Text style={{ fontSize: 11, color: C.textMuted, marginBottom: 4, fontWeight: '600' }}>From</Text>
                      {React.createElement('input', {
                        type: 'date',
                        value: bulkAllStartDate,
                        onChange: (e: any) => setBulkAllStartDate(e.target.value),
                        'data-testid': 'bulk-all-start-date',
                        style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: C.bgSoft, color: C.text, fontSize: 13, fontWeight: 600 },
                      })}
                    </View>
                    <View style={{ flex: 1, minWidth: 150 }}>
                      <Text style={{ fontSize: 11, color: C.textMuted, marginBottom: 4, fontWeight: '600' }}>To</Text>
                      {React.createElement('input', {
                        type: 'date',
                        value: bulkAllEndDate,
                        onChange: (e: any) => setBulkAllEndDate(e.target.value),
                        'data-testid': 'bulk-all-end-date',
                        style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: C.bgSoft, color: C.text, fontSize: 13, fontWeight: 600 },
                      })}
                    </View>
                    {(bulkAllStartDate || bulkAllEndDate) && (
                      <TouchableOpacity onPress={() => { setBulkAllStartDate(''); setBulkAllEndDate(''); }} style={{ alignSelf: 'flex-end', paddingVertical: 10, paddingHorizontal: 12 }} data-testid="bulk-all-clear-dates" testID="bulk-all-clear-dates">
                        <Text style={{ fontSize: 11, color: C.primary, fontWeight: '700' }}>Clear dates</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                  <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      data-testid="bulk-all-combined-pdf"
                      disabled={bulkAllExporting}
                      onClick={() => { void handleBulkAllExport('combined'); }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', borderRadius: 12, backgroundColor: colors.purple, border: 'none', color: colors.primaryText, fontSize: 13, fontWeight: 700, cursor: bulkAllExporting ? 'wait' : 'pointer', opacity: bulkAllExporting ? 0.6 : 1 }}
                    >
                      {bulkAllExporting ? 'Generating...' : 'Combined PDF'}
                    </button>
                    <button
                      type="button"
                      data-testid="bulk-all-zip"
                      disabled={bulkAllExporting}
                      onClick={() => { void handleBulkAllExport('zip'); }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', borderRadius: 12, backgroundColor: colors.info, border: 'none', color: colors.primaryText, fontSize: 13, fontWeight: 700, cursor: bulkAllExporting ? 'wait' : 'pointer', opacity: bulkAllExporting ? 0.6 : 1 }}
                    >
                      {bulkAllExporting ? 'Generating...' : 'Individual PDFs (ZIP)'}
                    </button>
                  </View>
                  {/* Divider */}
                  <View style={{ height: 1, backgroundColor: C.border, marginVertical: 16 }} />
                  {/* Email Yearly Summary */}
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.textMuted, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 12 }}>Email Annual Summary</Text>
                  <Text style={{ fontSize: 12, color: C.textMuted, marginBottom: 12, lineHeight: 18 }}>
                    Get a branded PDF with all receipts for a given year emailed to your inbox. Auto-sent every Jan 1st for the previous year.
                  </Text>
                  <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                    <View style={{ minWidth: 120 }}>
                      <Text style={{ fontSize: 11, color: C.textMuted, marginBottom: 4, fontWeight: '600' }}>Year</Text>
                      {React.createElement('select', {
                        value: selectedYear,
                        onChange: (e: any) => setSelectedYear(e.target.value),
                        'data-testid': 'yearly-summary-year-select',
                        style: { width: '100%', padding: '10px 12px', borderRadius: 10, border: `1px solid ${C.border}`, backgroundColor: C.bgSoft, color: C.text, fontSize: 13, fontWeight: 600, cursor: 'pointer' },
                      }, ...[...Array(5)].map((_, i) => {
                        const y = new Date().getFullYear() - i;
                        return React.createElement('option', { key: y, value: String(y) }, String(y));
                      }))}
                    </View>
                    <button
                      type="button"
                      data-testid="email-yearly-summary-btn"
                      disabled={emailingYearly}
                      onClick={() => { void handleEmailYearlySummary(); }}
                      style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 20px', borderRadius: 12, backgroundColor: colors.success, border: 'none', color: colors.primaryText, fontSize: 13, fontWeight: 700, cursor: emailingYearly ? 'wait' : 'pointer', opacity: emailingYearly ? 0.6 : 1 }}
                    >
                      {emailingYearly ? 'Sending...' : 'Email Yearly Summary'}
                    </button>
                  </View>
                  <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 10, lineHeight: 16 }}>
                    {bulkAllStartDate || bulkAllEndDate
                      ? `Exporting receipts${bulkAllStartDate ? ` from ${bulkAllStartDate}` : ''}${bulkAllEndDate ? ` to ${bulkAllEndDate}` : ''}`
                      : `All ${allItems.length} receipt(s) will be included`}
                  </Text>
                </View>
              )}
            </View>
          )}

          {/* Summary Cards */}
          <View style={{ paddingHorizontal: isWide ? 32 : 16, marginTop: 12, marginBottom: 16, flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 140, backgroundColor: summarySurface.successBg, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: summarySurface.successBorder }} testID="payment-history-summary-total" data-testid="payment-history-summary-total-card">
              <Ionicons name="wallet-outline" size={18} color={C.successText} />
              <Text style={{ fontSize: 11, color: summarySurface.successLabel, fontWeight: '700', marginTop: 6, textTransform: 'uppercase', letterSpacing: 0.6 }}>Total You Paid</Text>
              <Text style={{ fontSize: 24, fontWeight: '800', color: summarySurface.successText }}>${totalSpent.toFixed(2)}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 140, backgroundColor: summarySurface.infoBg, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: summarySurface.infoBorder }} testID="payment-history-summary-count" data-testid="payment-history-summary-count-card">
              <Ionicons name="receipt-outline" size={18} color={C.primary} />
              <Text style={{ fontSize: 11, color: summarySurface.infoLabel, fontWeight: '700', marginTop: 6, textTransform: 'uppercase', letterSpacing: 0.6 }}>Transactions</Text>
              <Text style={{ fontSize: 24, fontWeight: '800', color: summarySurface.infoText }}>{allItems.length}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 140, backgroundColor: summarySurface.warnBg, borderRadius: 20, padding: 16, borderWidth: 1, borderColor: summarySurface.warnBorder }} testID="payment-history-summary-plan" data-testid="payment-history-summary-plan-card">
              <Ionicons name="diamond-outline" size={18} color={C.warningText} />
              <Text style={{ fontSize: 11, color: summarySurface.warnLabel, fontWeight: '700', marginTop: 6, textTransform: 'uppercase', letterSpacing: 0.6 }}>Current Plan</Text>
              <Text style={{ fontSize: 24, fontWeight: '800', color: summarySurface.warnText }}>{getPlanName(user?.subscription_plan || 'free')}</Text>
            </View>
          </View>

          {/* Search / Filter Bar */}
          <View style={{ paddingHorizontal: isWide ? 32 : 16, marginBottom: 16 }} testID="payment-search-section">
            <View style={{ backgroundColor: summarySurface.panelBg, borderRadius: 16, padding: 14, borderWidth: 1, borderColor: summarySurface.panelBorder }}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>Search Payments</Text>
              {/* Mode Tabs */}
              <View style={{ flexDirection: 'row', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
                {([
                  { key: 'all', label: 'All', icon: 'list' },
                  { key: 'days', label: 'By Days', icon: 'today' },
                  { key: 'months', label: 'By Month', icon: 'calendar' },
                  { key: 'years', label: 'By Year', icon: 'time' },
                ] as const).map(m => (
                  <TouchableOpacity accessibilityLabel="Set search mode in payment history inner button"
                    key={m.key}
                    onPress={() => { setSearchMode(m.key); setSearchDays(''); setSearchMonth(''); setSearchYear(''); }}
                    style={{
                      flexDirection: 'row', alignItems: 'center', gap: 5,
                      paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8,
                      backgroundColor: searchMode === m.key ? C.primary : C.bgSoft,
                      borderWidth: 1, borderColor: searchMode === m.key ? C.primary : C.border,
                    }}
                    testID={`payment-search-mode-${m.key}`}
                  >
                    <Ionicons name={m.icon as any} size={13} color={searchMode === m.key ? C.primaryText : C.textMuted} />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: searchMode === m.key ? C.primaryText : C.textMuted }}>{m.label}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Search Inputs */}
              {searchMode === 'days' && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text style={{ fontSize: 12, color: C.textMuted }}>Last</Text>
                  <TextInput
                    value={searchDays} onChangeText={setSearchDays}
                    placeholder="e.g. 30" placeholderTextColor={C.textMuted}
                    keyboardType="numeric"
                    style={{ backgroundColor: C.bg, color: C.text, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: C.border, fontSize: 13, width: 80, textAlign: 'center' }}
                    testID="payment-search-days-input"
                  />
                  <Text style={{ fontSize: 12, color: C.textMuted }}>days</Text>
                </View>
              )}

              {searchMode === 'months' && (
                <View style={{ gap: 8 }}>
                  <Text style={{ fontSize: 11, color: C.textMuted, fontWeight: '600' }}>Select Month</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
                    {MONTHS.map((m, i) => (
                      <TouchableOpacity accessibilityLabel="Set search month in payment history inner button"
                        key={m}
                        onPress={() => { setSearchMonth(String(i + 1)); if (!searchYear) setSearchYear(String(currentYear)); }}
                        style={{
                          paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8,
                          backgroundColor: searchMonth === String(i + 1) ? C.primary : C.bgSoft,
                          borderWidth: 1, borderColor: searchMonth === String(i + 1) ? C.primary : C.border,
                        }}
                        testID={`payment-search-month-${i + 1}`}
                      >
                        <Text style={{ fontSize: 12, fontWeight: '700', color: searchMonth === String(i + 1) ? C.primaryText : C.textMuted }}>{m}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                  <Text style={{ fontSize: 11, color: C.textMuted, fontWeight: '600', marginTop: 4 }}>Year</Text>
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    {yearOptions.map(y => (
                      <TouchableOpacity accessibilityLabel="Set search year in payment history inner button"
                        key={y}
                        onPress={() => setSearchYear(String(y))}
                        style={{
                          paddingHorizontal: 14, paddingVertical: 7, borderRadius: 8,
                          backgroundColor: searchYear === String(y) ? C.primary : C.bgSoft,
                          borderWidth: 1, borderColor: searchYear === String(y) ? C.primary : C.border,
                        }}
                        testID={`payment-search-year-${y}`}
                      >
                        <Text style={{ fontSize: 12, fontWeight: '700', color: searchYear === String(y) ? C.primaryText : C.textMuted }}>{y}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              )}

              {searchMode === 'years' && (
                <View>
                  <Text style={{ fontSize: 11, color: C.textMuted, fontWeight: '600', marginBottom: 6 }}>Select Year</Text>
                  <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                    {yearOptions.map(y => (
                      <TouchableOpacity accessibilityLabel="Set search year in payment history inner button"
                        key={y}
                        onPress={() => setSearchYear(String(y))}
                        style={{
                          paddingHorizontal: 18, paddingVertical: 9, borderRadius: 8,
                          backgroundColor: searchYear === String(y) ? C.primary : C.bgSoft,
                          borderWidth: 1, borderColor: searchYear === String(y) ? C.primary : C.border,
                        }}
                        testID={`payment-search-year-btn-${y}`}
                      >
                        <Text style={{ fontSize: 13, fontWeight: '700', color: searchYear === String(y) ? C.primaryText : C.textMuted }}>{y}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              )}

              {/* Results count */}
              {searchMode !== 'all' && (
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border }}>
                  <Text style={{ fontSize: 12, color: C.textMuted }}>
                    Found <Text style={{ fontWeight: '700', color: C.text }}>{filteredItems.length}</Text> transaction{filteredItems.length !== 1 ? 's' : ''}
                    {filteredItems.length > 0 ? ` totaling ${formatAmount(filteredTotal, 'USD')}` : ''}
                  </Text>
                  <TouchableOpacity
                    accessibilityLabel="Clear"
                    onPress={() => { setSearchMode('all'); setSearchDays(''); setSearchMonth(''); setSearchYear(''); }}
                    data-testid="payment-search-clear" testID="payment-search-clear"
                  >
                    <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>Clear</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          </View>

          {/* Report Settings */}
          <View style={{ paddingHorizontal: isWide ? 32 : 16, marginBottom: 16 }}>
            <TouchableOpacity accessibilityLabel="mail button"
              onPress={() => setShowReportSettings(!showReportSettings)}
              style={{ backgroundColor: C.card, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: showReportSettings ? (globalThis as any).__alphaColor(C.primary, '40') : C.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
              testID="payment-report-settings-toggle"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Ionicons name="mail" size={18} color={C.primary} />
                <View>
                  <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>Email Reports</Text>
                  <Text style={{ fontSize: 11, color: C.textMuted }}>Get payment summaries in your inbox</Text>
                </View>
              </View>
              <Ionicons name={showReportSettings ? 'chevron-up' : 'chevron-down'} size={16} color={C.textMuted} />
            </TouchableOpacity>
            {showReportSettings && reportPrefs && (
              <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, marginTop: 8, borderWidth: 1, borderColor: C.border, gap: 12 }}>
                {/* Weekly toggle */}
                <TouchableOpacity accessibilityLabel="calendar outline button"
                  onPress={() => toggleReportPref('weekly_enabled')}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                  testID="report-toggle-weekly"
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="calendar-outline" size={16} color={colors.primary} />
                    </View>
                    <View>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Weekly Report</Text>
                      <Text style={{ fontSize: 10, color: C.textMuted }}>Every Monday at 8:30 AM UTC</Text>
                    </View>
                  </View>
                  <View style={{ width: 44, height: 26, borderRadius: 13, backgroundColor: reportPrefs.weekly_enabled ? C.primary : C.bgSoft, justifyContent: 'center', padding: 2, borderWidth: 1, borderColor: reportPrefs.weekly_enabled ? C.primary : C.border }}>
                    <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: C.primaryText, alignSelf: reportPrefs.weekly_enabled ? 'flex-end' : 'flex-start' }} />
                  </View>
                </TouchableOpacity>
                {/* Monthly toggle */}
                <TouchableOpacity accessibilityLabel="stats chart button"
                  onPress={() => toggleReportPref('monthly_enabled')}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                  testID="report-toggle-monthly"
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.purple, '15'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="stats-chart" size={16} color={colors.purpleText} />
                    </View>
                    <View>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Monthly Report</Text>
                      <Text style={{ fontSize: 10, color: C.textMuted }}>1st of each month at 8:30 AM UTC</Text>
                    </View>
                  </View>
                  <View style={{ width: 44, height: 26, borderRadius: 13, backgroundColor: reportPrefs.monthly_enabled ? C.primary : C.bgSoft, justifyContent: 'center', padding: 2, borderWidth: 1, borderColor: reportPrefs.monthly_enabled ? C.primary : C.border }}>
                    <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: C.primaryText, alignSelf: reportPrefs.monthly_enabled ? 'flex-end' : 'flex-start' }} />
                  </View>
                </TouchableOpacity>
                {/* Renewal Reminders toggle */}
                <TouchableOpacity accessibilityLabel="alarm button"
                  onPress={() => toggleReportPref('renewal_reminders')}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                  testID="report-toggle-renewal"
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(colors.error, '15'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="alarm" size={16} color={colors.error} />
                    </View>
                    <View>
                      <Text style={{ fontSize: 13, fontWeight: '600', color: C.text }}>Renewal Reminders</Text>
                      <Text style={{ fontSize: 10, color: C.textMuted }}>7 days and 1 day before expiry</Text>
                    </View>
                  </View>
                  <View style={{ width: 44, height: 26, borderRadius: 13, backgroundColor: reportPrefs.renewal_reminders ? C.primary : C.bgSoft, justifyContent: 'center', padding: 2, borderWidth: 1, borderColor: reportPrefs.renewal_reminders ? C.primary : C.border }}>
                    <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: C.primaryText, alignSelf: reportPrefs.renewal_reminders ? 'flex-end' : 'flex-start' }} />
                  </View>
                </TouchableOpacity>
                {/* Send Now */}
                <TouchableOpacity accessibilityLabel="Send report now button"
                  onPress={sendReportNow}
                  disabled={sendingReport}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30'), marginTop: 4, opacity: sendingReport ? 0.6 : 1 }}
                  testID="send-report-now-btn"
                >
                  <Ionicons name={sendingReport ? 'hourglass' : 'send'} size={14} color={C.primary} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary }}>{sendingReport ? 'Sending...' : 'Send Report Now'}</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Empty State */}
          {filteredItems.length === 0 && (
            <View style={{ alignItems: 'center', paddingVertical: 48, marginHorizontal: isWide ? 32 : 16, backgroundColor: C.card, borderRadius: 18, borderWidth: 1, borderColor: C.border }} testID="payment-history-empty">
              <View style={{ width: 72, height: 72, borderRadius: 36, backgroundColor: C.bgSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
                <Ionicons name="receipt-outline" size={36} color={C.textMuted} />
              </View>
              <Text style={{ fontSize: 17, fontWeight: '700', color: C.text, marginBottom: 6 }}>
                {searchMode === 'all' ? 'No Payments Yet' : 'No Results Found'}
              </Text>
              <Text style={{ fontSize: 13, color: C.textMuted, textAlign: 'center', paddingHorizontal: 24, lineHeight: 19 }}>
                {searchMode === 'all' ? 'Your payment history will appear here once you subscribe.' : 'Try adjusting your search filters to find transactions.'}
              </Text>
              {searchMode === 'all' && (
                <TouchableOpacity accessibilityLabel="View Plans"
                  style={{ backgroundColor: C.primary, paddingHorizontal: 24, paddingVertical: 10, borderRadius: 10, marginTop: 18 }}
                  onPress={() => router.push('/subscription/plans' as any)} testID="payment-history-subscribe-btn"
                >
                  <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '700' }}>View Plans</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {/* Payment Items */}
          {filteredItems.length > 0 && (
            <View style={{ paddingHorizontal: isWide ? 32 : 16 }} testID="payment-history-list">
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>
                  {searchMode === 'all' ? 'All Transactions' : 'Search Results'}
                </Text>
                {Platform.OS === 'web' && (
                  <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                    <TouchableOpacity onPress={toggleSelectAll} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="bulk-select-all" testID="bulk-select-all">
                      <View style={{ width: 18, height: 18, borderRadius: 4, borderWidth: 1.5, borderColor: selectedIds.size > 0 ? C.primary : C.textMuted, backgroundColor: selectedIds.size > 0 ? C.primary : 'transparent', alignItems: 'center', justifyContent: 'center' }}>
                        {selectedIds.size > 0 && <Ionicons name="checkmark" size={12} color={C.primaryText} />}
                      </View>
                      <Text style={{ fontSize: 11, fontWeight: '600', color: C.textMuted }}>{selectedIds.size > 0 ? `${selectedIds.size} selected` : 'Select All'}</Text>
                    </TouchableOpacity>
                  </View>
                )}
              </View>

              {/* Bulk Action Bar */}
              {selectedIds.size > 0 && Platform.OS === 'web' && (
                <View style={{ flexDirection: 'row', gap: 8, marginBottom: 12, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.primary, '10'), borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.primary, '30'), alignItems: 'center', flexWrap: 'wrap' }} data-testid="bulk-action-bar" testID="bulk-action-bar">
                  <Ionicons name="archive-outline" size={16} color={C.primary} />
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.primary, marginRight: 8 }}>{selectedIds.size} selected</Text>
                  <button
                    type="button"
                    data-testid="bulk-download-receipts"
                    disabled={bulkExporting}
                    onClick={() => { void handleBulkExport('receipt'); }}
                    style={{ padding: '8px 14px', borderRadius: 8, backgroundColor: colors.indigo, border: 'none', color: C.primaryText, fontSize: 11, fontWeight: 700, cursor: bulkExporting ? 'wait' : 'pointer', opacity: bulkExporting ? 0.6 : 1 }}
                  >
                    {bulkExporting ? 'Exporting...' : 'Download Receipts ZIP'}
                  </button>
                  <button
                    type="button"
                    data-testid="bulk-download-invoices"
                    disabled={bulkExporting}
                    onClick={() => { void handleBulkExport('invoice'); }}
                    style={{ padding: '8px 14px', borderRadius: 8, backgroundColor: colors.info, border: 'none', color: C.primaryText, fontSize: 11, fontWeight: 700, cursor: bulkExporting ? 'wait' : 'pointer', opacity: bulkExporting ? 0.6 : 1 }}
                  >
                    {bulkExporting ? 'Exporting...' : 'Download Invoices ZIP'}
                  </button>
                  <button
                    type="button"
                    data-testid="bulk-clear-selection"
                    onClick={() => setSelectedIds(new Set())}
                    style={{ padding: '8px 14px', borderRadius: 8, backgroundColor: 'transparent', border: `1px solid ${C.border}`, color: C.textMuted, fontSize: 11, fontWeight: 700, cursor: 'pointer' }}
                  >
                    Clear
                  </button>
                </View>
              )}

              {filteredItems.map((item, idx) => {
                const d = item.data;
                const method = d.payment_method || 'card';
                const status = item.type === 'payment' ? d.status : d.payment_status;
                const grossAmount = Number(d.amount_gross ?? d.total_amount ?? d.amount ?? 0);
                const customerChargeTotal = Number(d.total_amount ?? grossAmount ?? d.amount ?? 0);
                const taxAmount = Number(d.tax_amount ?? 0);
                const feeAmount = Number(d.processing_fee ?? d.fee ?? 0);
                const taxRatePercent = Number((Number(d.tax_rate ?? 0) * 100).toFixed(2));

                return (
                  <View key={`${item.type}-${idx}`} style={{ backgroundColor: enterpriseSurface.actionCardBg, borderRadius: 18, padding: isWide ? 18 : 14, marginBottom: 12, borderWidth: 1, borderColor: selectedIds.has(d.id || d.payment_id) ? C.primary : enterpriseSurface.actionCardBorder, shadowColor: colors.card, shadowOpacity: darkMode ? 0.22 : 0.06, shadowOffset: { width: 0, height: 6 }, shadowRadius: 14, elevation: 2 }} testID={`payment-history-item-${idx}`} data-testid={`payment-history-item-card-${idx}`}>
                    <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                      {Platform.OS === 'web' && item.type === 'payment' && (status === 'completed' || status === 'paid') && (
                        <TouchableOpacity
                          onPress={() => toggleSelect(d.id || d.payment_id)}
                          style={{ marginRight: 10 }}
                          data-testid={`select-payment-${idx}`} testID={`select-payment-${idx}`}
                        >
                          <View style={{
                            width: 20, height: 20, borderRadius: 5, borderWidth: 1.5,
                            borderColor: selectedIds.has(d.id || d.payment_id) ? C.primary : C.textMuted,
                            backgroundColor: selectedIds.has(d.id || d.payment_id) ? C.primary : 'transparent',
                            alignItems: 'center', justifyContent: 'center',
                          }}>
                            {selectedIds.has(d.id || d.payment_id) && <Ionicons name="checkmark" size={14} color={C.primaryText} />}
                          </View>
                        </TouchableOpacity>
                      )}
                      <View style={{ width: 42, height: 42, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(getMethodColor(method), '12'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={getMethodIcon(method)} size={20} color={getMethodColor(method)} />
                      </View>
                      <View style={{ flex: 1, marginLeft: 12 }}>
                        <Text style={{ fontSize: 14, fontWeight: '600', color: C.text }}>{getPlanName(d.plan_id)} Plan</Text>
                        <Text style={{ fontSize: 11, color: C.textMuted, marginTop: 2 }}>{formatDate(item.date)} at {formatTime(item.date)}</Text>
                      </View>
                      <View style={{ alignItems: 'flex-end' }}>
                        <Text style={{ fontSize: 16, fontWeight: '700', color: C.text }} data-testid={`payment-amount-${idx}`} testID={`payment-amount-${idx}`}>{formatAmount(customerChargeTotal, d.currency)}</Text>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: (globalThis as any).__alphaColor(getStatusColor(status), '15'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, marginTop: 3 }}>
                          <View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: getStatusColor(status) }} />
                          <Text style={{ fontSize: 10, fontWeight: '600', color: getStatusColor(status) }}>{getStatusLabel(status)}</Text>
                        </View>
                      </View>
                    </View>
                    {/* Details chips */}
                    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                        <Ionicons name={getMethodIcon(method)} size={11} color={C.textMuted} />
                        <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '500' }}>{getMethodLabel(method)}</Text>
                      </View>
                      {d.billing_period && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                          <Ionicons name="calendar-outline" size={11} color={C.textMuted} />
                          <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '500' }}>{d.billing_period}</Text>
                        </View>
                      )}
                      {d.currency && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                          <Text style={{ fontSize: 10, color: C.textMuted, fontWeight: '500' }}>{d.currency.toUpperCase()}</Text>
                        </View>
                      )}
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.warningSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }} data-testid={`payment-tax-fees-chip-${idx}`} testID={`payment-tax-fees-chip-${idx}`}>
                        <Ionicons name="cash-outline" size={11} color={colors.warningText} />
                        <Text style={{ fontSize: 10, color: colors.warningText, fontWeight: '700' }}>Applicable Tax: {formatAmount(taxAmount, d.currency)}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.warningSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }} data-testid={`payment-tax-rate-chip-${idx}`} testID={`payment-tax-rate-chip-${idx}`}>
                        <Ionicons name="pricetag-outline" size={11} color={colors.warningText} />
                        <Text style={{ fontSize: 10, color: colors.warningText, fontWeight: '700' }}>Tax %: {taxRatePercent}%</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: colors.purpleSoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }} data-testid={`payment-processing-fee-chip-${idx}`} testID={`payment-processing-fee-chip-${idx}`}>
                        <Ionicons name="card-outline" size={11} color={colors.purpleText} />
                        <Text style={{ fontSize: 10, color: colors.purpleText, fontWeight: '700' }}>Payment Processing Fee: {formatAmount(feeAmount, d.currency)}</Text>
                      </View>
                    </View>
                    {/* Action buttons for payment records */}
                    {item.type === 'payment' && d.id && (
                      <View style={{ marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: enterpriseSurface.cardBorderStrong, gap: 10 }}>
                        <View style={{ flexDirection: 'row', gap: 8 }}>
                              <TouchableOpacity accessibilityLabel="View Invoice"
                                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.primary + (darkMode ? '66' : '33'), backgroundColor: colors.primarySoft }}
                                onPress={() => openDocument(d.id, 'invoice')}
                                {...webClickProps(() => openDocument(d.id, 'invoice'))}
                                testID={`view-invoice-${idx}`}
                              >
                                <Ionicons name="eye-outline" size={13} color={colors.primary} />
                                <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primary }}>View Invoice</Text>
                              </TouchableOpacity>
                              <TouchableOpacity accessibilityLabel="View Receipt"
                                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.success + (darkMode ? '66' : '33'), backgroundColor: colors.successSoft }}
                                onPress={() => {
                                  if (status !== 'completed' && status !== 'paid') {
                                    setActionNotice('Receipt will be available once this payment is completed.');
                                    return;
                                  }
                                  openDocument(d.id, 'receipt');
                                }}
                                {...webClickProps(() => {
                                  if (status !== 'completed' && status !== 'paid') {
                                    setActionNotice('Receipt will be available once this payment is completed.');
                                    return;
                                  }
                                  openDocument(d.id, 'receipt');
                                })}
                                testID={`view-receipt-${idx}`}
                              >
                                <Ionicons name="eye-outline" size={13} color={darkMode ? colors.success : colors.success} />
                                <Text style={{ fontSize: 11, fontWeight: '700', color: darkMode ? colors.success : colors.success }}>View Receipt</Text>
                              </TouchableOpacity>
                        </View>
                        <View style={{ flexDirection: 'row', gap: 8 }}>
                              <TouchableOpacity accessibilityLabel="Download Receipt PDF"
                                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.indigo + (darkMode ? '70' : '33'), backgroundColor: colors.indigoSoft }}
                                onPress={() => {
                                  if (status !== 'completed' && status !== 'paid') {
                                    setActionNotice('Receipt PDF will be available once this payment is completed.');
                                    return;
                                  }
                                  downloadPdf(d.id, 'receipt');
                                }}
                                {...webClickProps(() => {
                                  if (status !== 'completed' && status !== 'paid') {
                                    setActionNotice('Receipt PDF will be available once this payment is completed.');
                                    return;
                                  }
                                  downloadPdf(d.id, 'receipt');
                                })}
                                testID={`pdf-receipt-${idx}`}
                              >
                                <Ionicons name="download-outline" size={13} color={darkMode ? colors.primary : colors.indigo} />
                                <Text style={{ fontSize: 11, fontWeight: '700', color: darkMode ? colors.primary : colors.indigo }}>Download Receipt PDF</Text>
                              </TouchableOpacity>
                              <TouchableOpacity accessibilityLabel="Download Invoice PDF"
                                style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.info + (darkMode ? '70' : '33'), backgroundColor: colors.infoSoft }}
                                onPress={() => downloadPdf(d.id, 'invoice')}
                                {...webClickProps(() => downloadPdf(d.id, 'invoice'))}
                                testID={`pdf-invoice-${idx}`}
                              >
                                <Ionicons name="download-outline" size={13} color={darkMode ? colors.infoText : colors.info} />
                                <Text style={{ fontSize: 11, fontWeight: '700', color: darkMode ? colors.infoText : colors.info }}>Download Invoice PDF</Text>
                              </TouchableOpacity>
                        </View>
                        <View style={{ flexDirection: 'row', gap: 8 }}>
                          <TouchableOpacity accessibilityLabel="Email receipt in payment history inner button"
                            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.purple + (darkMode ? '55' : '33'), backgroundColor: colors.purpleSoft, opacity: emailingReceipt === d.id ? 0.6 : 1 }}
                            onPress={() => emailReceipt(d.id)}
                            {...webClickProps(() => emailReceipt(d.id))}
                            disabled={emailingReceipt === d.id}
                            testID={`email-receipt-${idx}`}
                          >
                            <Ionicons name={emailingReceipt === d.id ? 'hourglass' : 'mail-outline'} size={13} color={darkMode ? colors.purpleText : colors.purple} />
                            <Text style={{ fontSize: 11, fontWeight: '600', color: darkMode ? colors.purpleText : colors.purple }}>{emailingReceipt === d.id ? 'Sending...' : 'Email Receipt'}</Text>
                          </TouchableOpacity>
                          <TouchableOpacity accessibilityLabel="Email invoice in payment history inner button"
                            style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.info + (darkMode ? '55' : '33'), backgroundColor: colors.infoSoft, opacity: emailingInvoice === d.id ? 0.6 : 1 }}
                            onPress={() => emailInvoice(d.id)}
                            {...webClickProps(() => emailInvoice(d.id))}
                            disabled={emailingInvoice === d.id}
                            testID={`email-invoice-${idx}`}
                          >
                            <Ionicons name={emailingInvoice === d.id ? 'hourglass' : 'send-outline'} size={13} color={darkMode ? colors.infoText : colors.info} />
                            <Text style={{ fontSize: 11, fontWeight: '600', color: darkMode ? colors.infoText : colors.info }}>{emailingInvoice === d.id ? 'Sending...' : 'Email Invoice'}</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
      </FadeSlideIn>
    </AppShell>
  );
}

export default function PaymentHistoryScreen() {
  return <PaymentHistoryV2 />;
}
