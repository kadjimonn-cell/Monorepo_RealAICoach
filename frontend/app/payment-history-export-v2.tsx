import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import AppShell from '../src/components/AppShell';
import { InlineNotice } from '../src/components/payment/InlineNotice';
import { ManualLinkPanel } from '../src/components/payment/ManualLinkPanel';
import { PreviewNoticeCard } from '../src/components/payment/PreviewNoticeCard';
import { PdfCanvasPreview } from '../src/components/payment/PdfCanvasPreview';
import { usePreviewLinkActions } from '../src/hooks/usePreviewLinkActions';
import api, { setCachedToken } from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { fetchPdfAsset, revokeObjectUrl, saveBlobWithBrowserFallback } from '../src/utils/paymentFileActions';
import { PaymentHistorySkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type Item = {
  id?: string;
  payment_id?: string;
  transaction_id?: string;
  session_id?: string;
  plan_id?: string;
  amount?: number;
  currency?: string;
  payment_method?: string;
  status?: string;
  payment_status?: string;
  created_at?: string;
};

const PLAN_NAMES: Record<string, string> = { basic: 'Basic', premium: 'Premium', free: 'Free' };

export default function PaymentHistoryExportPage() {
  const { t } = useTranslation();
  t('i18n.route.payment-history-export-v2.probe');
  const router = useRouter();
  const { colors } = useTheme();
  const { mode, auto } = useLocalSearchParams<{ mode?: string; auto?: string }>();
  const exportMode = String(mode || 'pdf').toLowerCase() === 'csv' ? 'csv' : String(mode || 'pdf').toLowerCase() === 'print' ? 'print' : 'pdf';
  const shouldAutoAction = ['1', 'true', 'yes'].includes(String(auto || '').toLowerCase());
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState<Item[]>([]);
  const [error, setError] = useState('');
  const [pdfUrl, setPdfUrl] = useState('');
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const [taxExporting, setTaxExporting] = useState(false);
  const autoActionStartedRef = useRef(false);
  const envReactBase = typeof process !== 'undefined' ? (process.env?.['REACT_APP_BACKEND_URL'] || '') : '';
  const envExpoBase = typeof process !== 'undefined' ? (process.env?.['EXPO_PUBLIC_BACKEND_URL'] || '') : '';
  const backendBaseUrl = (envReactBase || envExpoBase || '').replace(/\/$/, '');
  const brandLogoUrl = `${backendBaseUrl}/api/static/images/brand-logo-chip.png`;
  const isEmbeddedPreview = Platform.OS === 'web' && typeof window !== 'undefined' && window.top !== window.self;
  const webToken = Platform.OS === 'web' && typeof window !== 'undefined' ? (window.localStorage.getItem('session_token') || '') : '';
  const historyPdfUrl = `${backendBaseUrl}/api/r/x?f=p${webToken ? `&t=${encodeURIComponent(webToken)}` : ''}`;
  const historyCsvUrl = `${backendBaseUrl}/api/r/x?f=c${webToken ? `&t=${encodeURIComponent(webToken)}` : ''}`;
  const defaultPdfFilename = 'payment-history-enterprise.pdf';
  const manualUrl = exportMode === 'csv' ? historyCsvUrl : historyPdfUrl;
  const {
    actionNotice,
    copyManualLink: copyExportLink,
    manualLinkInputRef,
    selectManualLink: selectManualExportLink,
    setActionNotice,
  } = usePreviewLinkActions({
    copyFailureMessage: 'Unable to copy the export link automatically.',
    copySuccessMessage: `${exportMode.toUpperCase()} link copied. If App Preview blocks the direct handoff, paste the link into a new browser tab.`,
    manualUrl,
    selectMessage: `${exportMode.toUpperCase()} link selected below. Copy it manually from App Preview, then open it in a new browser tab if needed.`,
  });

  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    cardMuted: colors.cardMuted,
    border: colors.border,
    borderLight: colors.borderLight,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primary: colors.primary,
    indigo: colors.indigo,
    cyan: colors.info,
    bgSoft: colors.bgSoft,
    heroStart: colors.primary,
    heroMid: colors.indigo,
    heroEnd: colors.info,
  }), [colors]);

  const primaryActionGradient = 'linear-gradient(135deg, var(--app-primary), var(--app-info))';
  const secondaryActionGradient = 'linear-gradient(135deg, var(--app-info), var(--app-success))';
  const successActionGradient = 'linear-gradient(135deg, var(--app-success), var(--app-info))';
  const primaryActionShadow = `0 8px 22px ${(globalThis as any).__alphaColor(C.primary, '47')}`;
  const secondaryActionShadow = `0 8px 22px ${(globalThis as any).__alphaColor(C.cyan, '40')}`;
  const successActionShadow = `0 8px 22px ${(globalThis as any).__alphaColor(colors.successText, '42')}`;

  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const token = window.localStorage.getItem('session_token');
      if (token) setCachedToken(token);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const resp = await api.get('/payments/history');
        const merged = [...(resp.data.payments || []), ...(resp.data.transactions || [])]
          .sort((a: Item, b: Item) => new Date(String(b.created_at || '')).getTime() - new Date(String(a.created_at || '')).getTime());
        setItems(merged);
      } catch (error) {
        handleAppRecoverableError({
          scope: 'payment-history-export-v2.load-history',
          error,
          message: 'Unable to load payment history',
          setError,
          onRetry: () => { void load(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setError('Unable to load payment history');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const rows = items.map((item) => {
    const date = item.created_at ? new Date(item.created_at) : null;
    const rawStatus = String(item.status || item.payment_status || 'unknown');
    const normalizedStatus = rawStatus.replace(/_/g, ' ').trim();
    const status = normalizedStatus ? normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1) : 'Unknown';
    const reference = String(item.id || item.payment_id || item.transaction_id || item.session_id || '').trim() || '—';
    return {
      date: date && !Number.isNaN(date.getTime()) ? date.toLocaleString() : String(item.created_at || ''),
      reference,
      plan: `${PLAN_NAMES[String(item.plan_id || '')] || String(item.plan_id || 'Plan')} Plan`,
      amount: `$${Number((item.total_amount ?? item.amount_gross ?? item.amount) || 0).toFixed(2)}`,
      currency: String(item.currency || 'usd').toUpperCase(),
      method: (() => {
        const rawMethod = String(item.payment_method || 'card').toLowerCase();
        if (rawMethod.includes('kkiapay') || rawMethod.includes('mobile_money') || rawMethod.includes('fedapay')) {
          return 'FedaPay';
        }
        if (rawMethod.includes('stripe')) return 'Stripe';
        if (rawMethod.includes('paypal')) return 'PayPal';
        return String(item.payment_method || 'stripe').replace(/_/g, ' ').replace(/\b\w/g, (s) => s.toUpperCase());
      })(),
      status,
      source: item.session_id || item.transaction_id || item.payment_status ? 'Transactions' : 'Payments',
    };
  });

  const csvText = [
    'Date,Reference ID,Plan,Amount,Currency,Payment Method,Status,Source',
    ...rows.map((row) => `"${row.date}","${row.reference}","${row.plan}","${row.amount.replace('$', '')}","${row.currency}","${row.method}","${row.status}","${row.source}"`),
  ].join('\n');

  const totalSpent = items.reduce((sum, item) => {
    const s = String(item.status || item.payment_status || '').toLowerCase();
    return s === 'completed' || s === 'paid' ? sum + Number((item.total_amount ?? item.amount_gross ?? item.amount) || 0) : sum;
  }, 0);

  const generatedAtLabel = useMemo(
    () => new Date().toLocaleString('en-US', { month: 'long', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }),
    [],
  );

  const escapeHtml = (value: string) => value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const buildPrintHtml = () => {
    const logoMarkup = backendBaseUrl ? `<img src="${brandLogoUrl}" alt="RealAICoach logo" style="width:132px;max-width:100%;height:auto;display:block;margin-bottom:18px;" />` : '<div class="badge">RA</div>';
    const tableRows = rows.map((row) => `
      <tr>
        <td>${escapeHtml(row.date)}</td>
        <td>${escapeHtml(row.reference)}</td>
        <td>${escapeHtml(row.plan)}</td>
        <td>${escapeHtml(row.amount)} ${escapeHtml(row.currency)}</td>
        <td>${escapeHtml(row.method)}</td>
        <td>${escapeHtml(row.status)}</td>
        <td>${escapeHtml(row.source)}</td>
      </tr>
    `).join('');

    return `<!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8" />
          <title>Payment History</title>
          <style>
            :root { color-scheme: light; }
            body { margin: 0; padding: 32px; font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif; color: #0f172a; background: #f8fafc; } /* @theme-ok html-export-fixed-palette */
            .header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }
            .brand { display: flex; align-items: center; gap: 12px; }
            .badge { width: 42px; height: 42px; border-radius: 12px; background: #1d4ed8; color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700; }
            .title { font-size: 30px; font-weight: 900; margin: 18px 0 8px; letter-spacing: -0.6px; }
            .subtitle { color: #64748b; font-size: 14px; margin: 0; }
            .stats { display: flex; gap: 12px; margin: 20px 0 24px; }
            .stat { flex: 1; min-width: 180px; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 16px; padding: 16px; }
            .stat-label { color: #475569; font-size: 11px; text-transform: uppercase; font-weight: 700; letter-spacing: .08em; }
            .stat-value { color: #0f172a; font-size: 24px; font-weight: 800; margin-top: 6px; } /* @theme-ok html-export-fixed-palette */
            table { width: 100%; border-collapse: collapse; border: 1px solid #dbeafe; border-radius: 16px; overflow: hidden; background:#fff; box-shadow:0 8px 24px rgba(15,23,42,.06); }
            th { background: #1d4ed8; color: #ffffff; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; text-align: left; padding: 12px; }
            td { padding: 12px; border-top: 1px solid #e2e8f0; font-size: 13px; vertical-align: top; }
            tr:nth-child(even) td { background: #f8fafc; }
            .footer { margin-top: 18px; color: #64748b; font-size: 12px; }
          </style>
        </head>
        <body>
          <div class="header">
            <div>
              <div class="brand">
                ${logoMarkup}
              </div>
              <div class="title">Payment History</div>
              <p class="subtitle">Generated from your secure billing history.</p>
            </div>
            <div style="font-size: 12px; color: #475569; text-align: right;">
              <div style="text-transform: uppercase; font-weight: 700; letter-spacing: .08em;">Generated</div>
              <div style="margin-top: 6px; font-weight: 700;">${escapeHtml(generatedAtLabel)}</div>
            </div>
          </div>
          <div class="stats">
            <div class="stat">
              <div class="stat-label">Total You Paid</div>
              <div class="stat-value">$${totalSpent.toFixed(2)}</div>
            </div>
            <div class="stat">
              <div class="stat-label">Transactions</div>
              <div class="stat-value">${rows.length}</div>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Reference</th>
                <th>Plan</th>
                <th>Amount</th>
                <th>Method</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>${tableRows}</tbody>
          </table>
          <div class="footer">Generated by RealAICoach for your billing records.</div>
        </body>
      </html>`;
  };

  const printHtmlPreview = () => {
    if (typeof document === 'undefined') return;

    const iframe = document.createElement('iframe');
    iframe.style.position = 'fixed';
    iframe.style.right = '0';
    iframe.style.bottom = '0';
    iframe.style.width = '0';
    iframe.style.height = '0';
    iframe.style.border = '0';
    document.body.appendChild(iframe);

    const frameDoc = iframe.contentDocument || iframe.contentWindow?.document;
    if (!frameDoc) {
      document.body.removeChild(iframe);
      return;
    }

    frameDoc.open();
    frameDoc.write(buildPrintHtml());
    frameDoc.close();

    window.setTimeout(() => {
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
      window.setTimeout(() => {
        if (document.body.contains(iframe)) document.body.removeChild(iframe);
      }, 1200);
    }, 350);
  };

  const updatePdfUrl = (nextUrl: string) => {
    setPdfUrl((currentUrl) => {
      if (currentUrl && currentUrl !== nextUrl && typeof window !== 'undefined') {
        revokeObjectUrl(currentUrl);
      }
      return nextUrl;
    });
  };

  const loadPdfPreview = async () => {
    if (Platform.OS !== 'web' || exportMode === 'csv' || pdfLoading) return '';
    if (pdfUrl) return pdfUrl;

    setPdfLoading(true);
    setPdfError('');
    try {
      const asset = await fetchPdfAsset({ fallbackFilename: defaultPdfFilename, token: webToken, url: historyPdfUrl });
      updatePdfUrl(asset.objectUrl);
      return asset.objectUrl;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'payment-history-export-v2.load-pdf-preview',
        error,
        message: 'Unable to load the payment history PDF inside App Preview.',
        setError: setPdfError,
        onRetry: () => { void loadPdfPreview(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setPdfError('Unable to load the payment history PDF inside App Preview.');
      return '';
    } finally {
      setPdfLoading(false);
    }
  };

  const downloadPdf = (showNotice = true) => {
    if (Platform.OS !== 'web') return;
    if (isEmbeddedPreview) {
      setActionNotice('Preparing payment history PDF…');
      return;
    }
    const anchor = document.createElement('a');
    anchor.href = historyPdfUrl;
    anchor.download = defaultPdfFilename;
    anchor.rel = 'noopener';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    if (showNotice) setActionNotice('Payment history PDF download started.');
  };

  const downloadCsv = (showNotice = true) => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    if (isEmbeddedPreview) {
      setActionNotice('Preparing payment history CSV…');
      return;
    }
    const csvBlob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
    const csvUrl = window.URL.createObjectURL(csvBlob);
    const anchor = document.createElement('a');
    anchor.href = csvUrl;
    anchor.download = 'payment-history-enterprise.csv';
    anchor.rel = 'noopener';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    window.setTimeout(() => window.URL.revokeObjectURL(csvUrl), 60000);
    if (showNotice) setActionNotice('Payment history CSV download started.');
  };

  const handleTaxExport = async () => {
    if (Platform.OS !== 'web') return;
    setTaxExporting(true);
    try {
      const res = await api.get('/payments/tax-export', { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tax_export_${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      setActionNotice('Tax-ready CSV export downloaded.');
    } catch (error) {
      handleAppRecoverableError({
        scope: 'payment-history-export-v2.tax-export',
        error,
        message: 'Unable to export tax data. Please try again.',
        setError: setActionNotice,
        onRetry: () => { void handleTaxExport(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setActionNotice('Unable to export tax data. Please try again.');
    }
    setTaxExporting(false);
  };

  const handlePrint = async (showNotice = true) => {
    if (Platform.OS !== 'web') return;

    if (isEmbeddedPreview) {
      setActionNotice('Preparing payment history PDF…');
      return;
    }

    if (showNotice) setActionNotice('Opening print dialog…');
    printHtmlPreview();
  };

  const trySavePdfInPreview = async () => {
    if (Platform.OS !== 'web') return;
    const readyUrl = pdfUrl || await loadPdfPreview();
    if (!readyUrl) {
      setActionNotice('PDF is not ready yet. Please try again.');
      return;
    }

    const blob = await fetch(readyUrl).then((response) => response.blob());
    try {
      const result = await saveBlobWithBrowserFallback({ blob, filename: defaultPdfFilename });
      setActionNotice(result === 'saved' ? 'Payment history PDF saved successfully.' : result === 'shared' ? 'Share sheet opened for the PDF.' : 'Payment history PDF download started.');
      return;
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        setActionNotice('Save cancelled.');
        return;
      }
    }

    setActionNotice('App Preview blocked the PDF handoff. Use the manual link below.');
  };

  const trySaveCsvInPreview = async () => {
    if (Platform.OS !== 'web') return;
    const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
    const anyWindow = window as any;
    try {
      if (typeof anyWindow.showSaveFilePicker === 'function') {
        const handle = await anyWindow.showSaveFilePicker({
          suggestedName: 'payment-history-enterprise.csv',
          types: [{ description: 'CSV file', accept: { 'text/csv': ['.csv'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        setActionNotice('Payment history CSV saved successfully.');
        return;
      }
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        setActionNotice('Save cancelled.');
        return;
      }
    }

    try {
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = 'payment-history-enterprise.csv';
      anchor.rel = 'noopener';
      anchor.style.display = 'none';
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      window.setTimeout(() => window.URL.revokeObjectURL(objectUrl), 60000);
      setActionNotice('Payment history CSV download started.');
      return;
    } catch (error) { handleAppRecoverableError({ scope: 'payment-history-export-v2.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    setActionNotice('App Preview blocked the CSV handoff. Use the manual link below.');
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || loading || error || exportMode === 'csv') return;
    loadPdfPreview();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, error, exportMode]);

  useEffect(() => {
    if (Platform.OS !== 'web' || isEmbeddedPreview || loading || !!error || !shouldAutoAction || autoActionStartedRef.current) return;

    autoActionStartedRef.current = true;
    const timer = window.setTimeout(() => {
      if (exportMode === 'csv') {
        downloadCsv();
        return;
      }
      if (exportMode === 'print') {
        handlePrint();
        return;
      }
      downloadPdf();
    }, 280);

    return () => window.clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAutoAction, exportMode, isEmbeddedPreview, loading, error]);

  useEffect(() => () => {
    if (pdfUrl && typeof window !== 'undefined') {
      revokeObjectUrl(pdfUrl);
    }
  }, [pdfUrl]);

  if (loading) {
    return <AppShell><PaymentHistorySkeleton /></AppShell>;
  }

  if (error) {
    return <AppShell><SafeAreaView style={{ flex: 1, backgroundColor: C.bg, alignItems: 'center', justifyContent: 'center', padding: 24 }}><Text data-testid="payment-history-export-error" testID="payment-history-export-error" style={{ color: C.text, fontWeight: '700' }}>{error}</Text></SafeAreaView></AppShell>;
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          <View style={{ backgroundColor: C.card, borderRadius: 24, borderWidth: 1, borderColor: C.border, overflow: 'hidden', shadowColor: colors.shadowColor, shadowOpacity: 0.08, shadowOffset: { width: 0, height: 8 }, shadowRadius: 18, elevation: 3 }} data-testid="payment-history-export-page" testID="payment-history-export-page">
            <LinearGradient colors={[C.heroStart, C.heroMid, C.heroEnd]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ padding: 20 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap', marginBottom: 14 }}>
              <View style={{ alignSelf: 'flex-start' }}>
                {Platform.OS === 'web'
                  ? React.createElement('img', {
                      src: brandLogoUrl,
                      alt: 'RealAICoach full logo',
                      'data-testid': 'payment-history-export-brand-logo',
                      style: { width: '132px', maxWidth: '100%', height: 'auto', display: 'block' },
                    })
                  : <Image source={require('../assets/images/brand-logo-chip.png')} style={{ width: 132, height: 42 }} resizeMode="contain" testID="payment-history-export-brand-logo" />}
              </View>
              <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.16)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.24)' }} data-testid="payment-history-export-meta-pill" testID="payment-history-export-meta-pill">
                <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>{t("gallery.featureDetail.export.generated")}</Text>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 4 }}>{generatedAtLabel}</Text>
              </View>
            </View>
            <Text data-testid="payment-history-export-title" testID="payment-history-export-title" style={{ color: colors.text, fontSize: 30, fontWeight: '900', letterSpacing: -0.6 }}>
              {exportMode === 'csv' ? 'Payment History CSV' : exportMode === 'print' ? 'Print Payment History' : 'Payment History PDF'}
            </Text>
            <Text style={{ color: colors.primaryText, marginTop: 10 }} data-testid="payment-history-export-subtitle" testID="payment-history-export-subtitle">
              {exportMode === 'csv' ? 'Review, copy, or download your CSV export below.' : 'Review, download, or print your payment history from this secure export page.'}
            </Text>
            <Text data-testid="payment-history-export-summary" testID="payment-history-export-summary" style={{ color: colors.text, fontWeight: '700', marginTop: 12 }}>{t("autofix.watchSweep1.total.spent.2")}{totalSpent.toFixed(2)}{t("autofix.watchSweep1.rows")}{rows.length}
            </Text>
            </LinearGradient>

            <View style={{ padding: 20 }}>
            {isEmbeddedPreview && exportMode !== 'csv' && (
              <PreviewNoticeCard
                backgroundColor={colors.primarySoft}
                borderColor={colors.primarySoft}
                message="Chrome blocks the inline PDF viewer here, so this page keeps the payment history visible and provides preview-safe save/download actions instead."
                messageColor={colors.primary}
                testId="payment-history-export-preview-banner"
                title="App Preview PDF mode"
                titleColor={colors.primary}
              />
            )}
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: isEmbeddedPreview && exportMode !== 'csv' ? 6 : 2 }}>
              {Platform.OS === 'web' ? (
                <>
                  {exportMode === 'csv' ? (
                    isEmbeddedPreview ? (
                      <button
                        type="button"
                        data-testid="payment-history-export-download-csv-button"
                        onClick={() => { void trySaveCsvInPreview(); }}
                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: primaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: primaryActionShadow }}
                      >{t("autofix.watchSweep1.save.csv")}</button>
                    ) : (
                      <button
                        type="button"
                        data-testid="payment-history-export-download-csv-button"
                        onClick={downloadCsv}
                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: primaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: primaryActionShadow }}
                      >{t("autofix.download.csv")}</button>
                    )
                  ) : (
                    <>
                      {isEmbeddedPreview ? (
                        <>
                          <button
                            type="button"
                            data-testid="payment-history-export-print-button"
                            onClick={() => { void trySavePdfInPreview(); }}
                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: primaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: primaryActionShadow }}
                          >{t("autofix.watchSweep1.save.pdf")}</button>
                          <button
                            type="button"
                            data-testid="payment-history-export-download-pdf-button"
                            onClick={selectManualExportLink}
                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: secondaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: secondaryActionShadow }}
                          >{t("autofix.watchSweep1.select.download.link")}</button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            data-testid="payment-history-export-print-button"
                            onClick={() => { void handlePrint(); }}
                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: primaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: primaryActionShadow }}
                          >{t("autofix.watchSweep1.print.save.as.pdf")}</button>
                          <button
                            type="button"
                            data-testid="payment-history-export-download-pdf-button"
                            onClick={() => { void downloadPdf(); }}
                            style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: secondaryActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: secondaryActionShadow }}
                          >{t("autofix.download.pdf")}</button>
                        </>
                      )}
                    </>
                  )}
                  <button
                    type="button"
                    data-testid="payment-history-export-back-button"
                    onClick={() => router.push('/payment-history' as any)}
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, backgroundColor: C.bgSoft, border: `1px solid ${C.border}`, color: C.text, fontWeight: 700, cursor: 'pointer' }}
                  >{t("autofix.back.to.payment.history")}</button>
                  {isEmbeddedPreview && (
                    <button
                      type="button"
                      data-testid="payment-history-export-copy-link-button"
                      onClick={() => { void copyExportLink(); }}
                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, backgroundColor: 'transparent', border: `1px dashed ${C.border}`, color: C.textMuted, fontWeight: 700, cursor: 'pointer' }}
                    >{t("referrals.actions.copy")}{exportMode === 'csv' ? 'CSV' : 'PDF'}{t("autofix.watchSweep1.link")}</button>
                  )}
                  <button
                    type="button"
                    data-testid="tax-export-csv-button"
                    disabled={taxExporting}
                    onClick={() => { void handleTaxExport(); }}
                    style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '12px 18px', borderRadius: 999, background: successActionGradient, border: 'none', color: colors.primaryText, fontWeight: 700, cursor: taxExporting ? 'wait' : 'pointer', opacity: taxExporting ? 0.7 : 1, boxShadow: successActionShadow }}
                  >
                    {taxExporting ? 'Exporting...' : 'Tax Export CSV'}
                  </button>
                </>
              ) : (
                <>
                  {exportMode === 'csv' ? (
                    <TouchableOpacity data-testid="payment-history-export-download-csv-button" testID="payment-history-export-download-csv-button" onPress={downloadCsv} style={{ backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("autofix.download.csv")}</Text>
                    </TouchableOpacity>
                  ) : (
                    <>
                      <TouchableOpacity data-testid="payment-history-export-print-button" testID="payment-history-export-print-button" onPress={() => { void handlePrint(); }} style={{ backgroundColor: colors.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                        <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{isEmbeddedPreview ? 'Save Payment History PDF' : 'Print / Save as PDF'}</Text>
                      </TouchableOpacity>
                      <TouchableOpacity data-testid="payment-history-export-download-pdf-button" testID="payment-history-export-download-pdf-button" onPress={() => { void downloadPdf(); }} style={{ backgroundColor: colors.indigo, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                        <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("autofix.download.pdf")}</Text>
                      </TouchableOpacity>
                    </>
                  )}
                  <TouchableOpacity data-testid="payment-history-export-back-button" testID="payment-history-export-back-button" onPress={() => router.push('/payment-history' as any)} style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                    <Text style={{ color: C.text, fontWeight: '700' }}>{t("autofix.back.to.payment.history")}</Text>
                  </TouchableOpacity>
                  {isEmbeddedPreview && (
                    <TouchableOpacity data-testid="payment-history-export-copy-link-button" testID="payment-history-export-copy-link-button" onPress={() => { void copyExportLink(); }} style={{ backgroundColor: 'transparent', borderWidth: 1, borderStyle: 'dashed', borderColor: C.border, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: C.textMuted, fontWeight: '700' }}>{t("referrals.actions.copy")}{exportMode === 'csv' ? 'CSV' : 'PDF'}{t("autofix.watchSweep1.link")}</Text>
                    </TouchableOpacity>
                  )}
                </>
              )}
            </View>
            {!!actionNotice && <InlineNotice backgroundColor={C.bgSoft} borderColor={C.border} message={actionNotice} testId="payment-history-export-action-notice" textColor={C.text} />}
            {isEmbeddedPreview && (
              <ManualLinkPanel
                backgroundColor={C.bgSoft}
                borderColor={C.border}
                inputRef={(node: any) => { manualLinkInputRef.current = node; }}
                inputTestId="payment-history-export-manual-link-input"
                label={`Manual ${exportMode === 'csv' ? 'CSV' : 'PDF'} Link`}
                panelTestId="payment-history-export-manual-link-panel"
                textColor={C.text}
                value={exportMode === 'csv' ? historyCsvUrl : historyPdfUrl}
              />
            )}

            {exportMode === 'csv' ? (
              <View style={{ marginTop: 18, backgroundColor: C.cardMuted || C.card, borderRadius: 18, padding: 16 }}>
                <Text data-testid="payment-history-export-csv-content" testID="payment-history-export-csv-content" style={{ color: C.textSec, fontFamily: Platform.OS === 'web' ? 'monospace' : undefined }}>
                  {csvText}
                </Text>
              </View>
            ) : (
              <View style={{ marginTop: 18 }}>
                <View style={{ marginBottom: 18 }} data-testid="payment-history-export-pdf-preview" testID="payment-history-export-pdf-preview">
                  <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700', marginBottom: 12 }}>{isEmbeddedPreview ? 'PDF FILE STATUS' : 'LIVE PDF STATUS'}</Text>
                  {pdfLoading && (
                    <PaymentHistorySkeleton />
                  )}
                  {!pdfLoading && !pdfUrl && (
                    <View style={{ minHeight: 160, borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 20, alignItems: 'center', justifyContent: 'center' }} data-testid="payment-history-export-pdf-error" testID="payment-history-export-pdf-error">
                      <Ionicons name="alert-circle-outline" size={28} color={colors.warningText} />
                      <Text style={{ color: C.text, fontWeight: '700', textAlign: 'center', marginTop: 10 }}>{pdfError || 'The payment history PDF file is not ready yet.'}</Text>
                      <Text style={{ color: C.textMuted, textAlign: 'center', marginTop: 8 }}>{t("autofix.watchSweep1.try.the.download.pdf.button.above.again.in")}</Text>
                    </View>
                  )}
                  {!pdfLoading && !!pdfUrl && (
                    <PdfCanvasPreview
                      accentColor={C.primary}
                      backgroundColor={C.bgSoft}
                      borderColor={C.border}
                      directUrl={historyPdfUrl}
                      emptyMessage="Waiting for PDF data..."
                      errorMessage="Unable to render the payment history PDF inline."
                      mutedColor={C.textMuted}
                      pdfUrl={pdfUrl}
                      testIdPrefix="payment-history-export-pdf-canvas"
                      textColor={C.text}
                      title=""
                    />
                  )}
                </View>
                <View style={{ marginBottom: 18 }} data-testid="payment-history-export-inline-preview" testID="payment-history-export-inline-preview">
                  <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700', marginBottom: 12 }}>{isEmbeddedPreview ? 'INLINE PDF PREVIEW' : 'LIVE EXPORT PREVIEW'}</Text>
                  <View style={{ borderRadius: 22, borderWidth: 1, borderColor: C.borderLight || C.border, backgroundColor: C.card, padding: 18 }}>
                    <View style={{ borderRadius: 16, borderWidth: 1, borderColor: C.borderLight || C.border, backgroundColor: C.bgSoft, padding: 14 }}>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                        <View style={{ gap: 8 }}>
                          <View style={{ alignSelf: 'flex-start' }}>
                          {Platform.OS === 'web' && React.createElement('img', {
                            src: brandLogoUrl,
                            alt: 'RealAICoach full logo',
                            'data-testid': 'payment-history-export-inline-preview-logo',
                            style: { width: '128px', maxWidth: '100%', height: 'auto', objectFit: 'contain', display: 'block' },
                          })}
                          {Platform.OS !== 'web' && <Image source={require('../assets/images/brand-logo-chip.png')} style={{ width: 128, height: 40 }} resizeMode="contain" testID="payment-history-export-inline-preview-logo" />}
                          </View>
                          <Text style={{ color: C.textMuted, fontSize: 11 }}>{t("autofix.watchSweep1.commercial.payment.activity.report")}</Text>
                        </View>
                        <View>
                          <Text style={{ color: C.textMuted, fontSize: 10, textTransform: 'uppercase', fontWeight: '700' }}>{t("gallery.featureDetail.export.generated")}</Text>
                          <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', marginTop: 3 }}>{generatedAtLabel}</Text>
                        </View>
                      </View>
                    </View>

                    <Text style={{ color: C.text, fontSize: 28, fontWeight: '800', marginTop: 20 }}>{t("nav.paymentHistory")}</Text>
                    <Text style={{ color: C.textMuted, marginTop: 6 }}>{isEmbeddedPreview ? 'Generated in App Preview — preview-safe commercial statement' : 'Desktop-safe live preview of the exported PDF content'}</Text>

                    <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap', marginTop: 18, marginBottom: 20 }}>
                      <View style={{ flex: 1, minWidth: 120, borderRadius: 16, borderWidth: 1, borderColor: C.borderLight || C.border, backgroundColor: C.bgSoft, padding: 14 }}>
                        <Text style={{ color: C.textSec, fontSize: 10, textTransform: 'uppercase', fontWeight: '700' }}>{t("paymentHistory.header.totalPaid")}</Text>
                        <Text style={{ color: C.text, fontSize: 24, fontWeight: '800', marginTop: 6 }}>${totalSpent.toFixed(2)}</Text>
                      </View>
                      <View style={{ flex: 1, minWidth: 120, borderRadius: 16, borderWidth: 1, borderColor: C.borderLight || C.border, backgroundColor: C.bgSoft, padding: 14 }}>
                        <Text style={{ color: C.textSec, fontSize: 10, textTransform: 'uppercase', fontWeight: '700' }}>{t("iapManagement.tabs.transactions")}</Text>
                        <Text style={{ color: C.text, fontSize: 24, fontWeight: '800', marginTop: 6 }}>{rows.length}</Text>
                      </View>
                    </View>

                    <View style={{ borderWidth: 1, borderColor: C.borderLight || C.border, borderRadius: 16, overflow: 'hidden' }}>
                      <View style={{ flexDirection: 'row', backgroundColor: colors.primary, paddingVertical: 10, paddingHorizontal: 12 }}>
                        {['Date', 'Reference', 'Plan', 'Amount', 'Method', 'Status', 'Source'].map((label) => (
                          <Text key={label} style={{ flex: 1, color: colors.text, fontSize: 11, fontWeight: '700' }}>{label}</Text>
                        ))}
                      </View>
                      {rows.slice(0, 6).map((row, index) => (
                        <View key={`${row.date}-${index}-preview`} style={{ flexDirection: 'row', paddingVertical: 11, paddingHorizontal: 12, backgroundColor: index % 2 === 0 ? C.card : C.bgSoft, borderTopWidth: index === 0 ? 0 : 1, borderTopColor: C.border }}>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.date}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.reference}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.plan}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.amount}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.method}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.status}</Text>
                          <Text style={{ flex: 1, color: C.text, fontSize: 11 }}>{row.source}</Text>
                        </View>
                      ))}
                    </View>

                    <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 14 }}>{isEmbeddedPreview ? 'This inline card mirrors the upgraded commercial-grade PDF styling while keeping the App Preview experience readable.' : 'This desktop-safe HTML preview replaces the fragile embedded PDF frame while keeping the same billing data readable before or after download.'}</Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  {['Date', 'Reference', 'Plan', 'Amount', 'Method', 'Status', 'Source'].map((label) => (
                    <Text key={label} style={{ flex: 1, color: C.textMuted, fontSize: 12, fontWeight: '700' }}>{label}</Text>
                  ))}
                </View>
                {rows.map((row, index) => (
                  <View key={`${row.date}-${index}`} style={{ flexDirection: 'row', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.border }} data-testid={`payment-history-export-row-${index}`} testID={`payment-history-export-row-${index}`}>
                    <Text style={{ flex: 1, color: C.text }}>{row.date}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.reference}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.plan}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.amount}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.method}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.status}</Text>
                    <Text style={{ flex: 1, color: C.text }}>{row.source}</Text>
                  </View>
                ))}
              </View>
            )}
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}