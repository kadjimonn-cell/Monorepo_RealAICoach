import React, { useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Linking, Platform, Image } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { LinearGradient } from 'expo-linear-gradient';
import AppShell from '../src/components/AppShell';
import { InlineNotice } from '../src/components/payment/InlineNotice';
import { BillingGlossaryLabel } from '../src/components/payment/BillingGlossaryTooltip';
import { ManualLinkPanel } from '../src/components/payment/ManualLinkPanel';
import { PreviewNoticeCard } from '../src/components/payment/PreviewNoticeCard';
import { PdfCanvasPreview } from '../src/components/payment/PdfCanvasPreview';
import { usePreviewLinkActions } from '../src/hooks/usePreviewLinkActions';
import api, { setCachedToken } from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { fetchPdfAsset, revokeObjectUrl, saveBlobWithBrowserFallback } from '../src/utils/paymentFileActions';
import { PaymentHistorySkeleton } from '../src/components/SkeletonLoaders';
import { useTranslation } from '../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

type PaymentDoc = {
  id?: string;
  payment_id?: string;
  session_id?: string;
  plan_id?: string;
  billing_period?: string;
  amount?: number;
  subtotal?: number;
  tax_amount?: number;
  processing_fee?: number;
  total_amount?: number;
  currency?: string;
  payment_method?: string;
  status?: string;
  payment_status?: string;
  created_at?: string;
};

const PLAN_NAMES: Record<string, string> = { basic: 'Basic', premium: 'Premium', free: 'Free' };

export default function PaymentDocumentPage() {
  const { t } = useTranslation();
  t('i18n.route.payment-document-v2.probe');
  const router = useRouter();
  const { user } = useAuth();
  const { colors } = useTheme();
  const params = useLocalSearchParams<{ paymentId?: string; docType?: string; action?: string; auto?: string; tm?: string }>();
  const paymentId = String(params.paymentId || '');
  const docType = String(params.docType || 'receipt') === 'invoice' ? 'invoice' : 'receipt';
  const action = String(params.action || 'view');
  const transparencyMode = !['0', 'false', 'off'].includes(String(params.tm || '1').toLowerCase());
  const shouldAutoAction = ['1', 'true', 'yes'].includes(String(params.auto || '').toLowerCase());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [doc, setDoc] = useState<PaymentDoc | null>(null);
  const [pdfUrl, setPdfUrl] = useState('');
  const [pdfFilename, setPdfFilename] = useState('');
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const autoActionStartedRef = useRef(false);
  const envReactBase = typeof process !== 'undefined' ? (process.env?.['REACT_APP_BACKEND_URL'] || '') : '';
  const envExpoBase = typeof process !== 'undefined' ? (process.env?.['EXPO_PUBLIC_BACKEND_URL'] || '') : '';
  const backendBaseUrl = (envReactBase || envExpoBase || '').replace(/\/$/, '');
  const brandLogoUrl = `${backendBaseUrl}/api/static/images/brand-logo-chip.png`;
  const isEmbeddedPreview = Platform.OS === 'web' && typeof window !== 'undefined' && window.top !== window.self;

  // Force light/white palette for the receipt card — documents must always be readable & printable
  const C = useMemo(() => ({
    bg: colors.bg,
    card: colors.card,
    border: colors.border,
    text: colors.text,
    textMuted: colors.textMuted,
    primary: colors.primary,
    indigo: colors.indigo,
    cyan: colors.info,
    bgSoft: colors.card,
    success: colors.success,
    heroStart: colors.primary,
    heroMid: colors.indigo,
    heroEnd: colors.info,
  }), [colors]);

  useEffect(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const token = window.localStorage.getItem('session_token');
      if (token) setCachedToken(token);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      if (!paymentId) {
        setError('Missing payment ID');
        setLoading(false);
        return;
      }
      try {
        const resp = await api.get('/payments/history');
        const payments = resp.data.payments || [];
        const transactions = resp.data.transactions || [];
        const found = [...payments, ...transactions].find((item: PaymentDoc) => (
          item.id === paymentId || item.payment_id === paymentId || item.session_id === paymentId
        ));
        if (!found) {
          setError('Payment not found');
        } else {
          setDoc(found);
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'payment-document-v2.load-document',
          error,
          message: 'Unable to load document',
          setError,
          onRetry: () => { void load(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setError('Unable to load document');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [paymentId]);

  const subtotal = Number(doc?.subtotal ?? doc?.amount ?? 0);
  const taxAmount = Number(doc?.tax_amount ?? 0);
  const processingFee = Number(doc?.processing_fee ?? 0);
  const totalAmount = Number(doc?.total_amount ?? (subtotal + taxAmount + processingFee));
  const netSettlement = Number((totalAmount - processingFee).toFixed(2));
  const planName = PLAN_NAMES[String(doc?.plan_id || '')] || String(doc?.plan_id || 'Plan');
  const paymentMethodRaw = String(doc?.payment_method || 'card').toLowerCase();
  const paymentMethod = paymentMethodRaw.includes('kkiapay')
    ? 'FedaPay'
    : paymentMethodRaw.includes('mobile_money') || paymentMethodRaw.includes('fedapay')
      ? 'FedaPay'
      : paymentMethodRaw.includes('stripe')
        ? 'Stripe'
        : paymentMethodRaw.includes('paypal')
          ? 'PayPal'
          : String(doc?.payment_method || 'stripe').replace(/_/g, ' ');
  const status = String(doc?.status || doc?.payment_status || 'completed');
  const statusLabel = status === 'completed' || status === 'paid' ? 'Paid' : status;
  const created = doc?.created_at ? new Date(doc.created_at) : null;
  const dateLabel = created && !Number.isNaN(created.getTime()) ? created.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }) : String(doc?.created_at || '');
  const shortId = String(doc?.payment_id || doc?.id || doc?.session_id || paymentId).slice(0, 12).toUpperCase();
  const backendDocType = docType === 'receipt' ? 'r' : 'i';
  const csvDocType = docType === 'receipt' ? 'receipt' : 'invoice';
  const webToken = Platform.OS === 'web' && typeof window !== 'undefined' ? (window.localStorage.getItem('session_token') || '') : '';
  const fileUrl = `${backendBaseUrl}/api/r/f?d=${backendDocType}&p=${encodeURIComponent(paymentId)}&v=0&tm=${transparencyMode ? '1' : '0'}&cb=${Date.now()}${webToken ? `&t=${encodeURIComponent(webToken)}` : ''}`;
  const csvFileUrl = `${backendBaseUrl}/api/payments/${csvDocType}/${encodeURIComponent(paymentId)}/csv${webToken ? `?t=${encodeURIComponent(webToken)}` : ''}`;
  const defaultFilename = `pdf-v15-for-attachment-${docType}_${String(doc?.payment_id || doc?.id || doc?.session_id || paymentId || 'payment')}.pdf`;
  const {
    actionNotice,
    copyManualLink: copyPdfLink,
    manualLinkInputRef,
    selectManualLink: selectManualPdfLink,
    setActionNotice,
  } = usePreviewLinkActions({
    copyFailureMessage: 'Unable to copy the PDF link automatically.',
    copySuccessMessage: 'PDF link copied. If App Preview blocks the direct handoff, paste the link into a new browser tab.',
    manualUrl: fileUrl,
    selectMessage: 'PDF link selected below. Copy it manually from App Preview, then open it in a new browser tab if needed.',
  });

  const updatePdfUrl = (nextUrl: string) => {
    setPdfUrl((currentUrl) => {
      if (currentUrl && currentUrl !== nextUrl && typeof window !== 'undefined') {
        revokeObjectUrl(currentUrl);
      }
      return nextUrl;
    });
  };

  const loadPdfPreview = async () => {
    if (Platform.OS !== 'web' || !paymentId || pdfLoading) return '';

    if (pdfUrl) return pdfUrl;

    setPdfLoading(true);
    setPdfError('');
    try {
      const asset = await fetchPdfAsset({ fallbackFilename: defaultFilename, token: webToken, url: fileUrl });
      updatePdfUrl(asset.objectUrl);
      setPdfFilename(asset.filename);
      return asset.objectUrl;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'payment-document-v2.load-pdf-preview',
        error,
        message: 'Unable to load the PDF inside App Preview.',
        setError: setPdfError,
        onRetry: () => { void loadPdfPreview(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setPdfError('Unable to load the PDF inside App Preview.');
      return '';
    } finally {
      setPdfLoading(false);
    }
  };

  const downloadWebPdf = async () => {
    if (Platform.OS !== 'web') return;

    const readyUrl = pdfUrl || await loadPdfPreview();
    if (!readyUrl || typeof document === 'undefined') return;

    const anchor = document.createElement('a');
    anchor.href = readyUrl;
    anchor.download = pdfFilename || defaultFilename;
    anchor.rel = 'noopener';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  const getPdfBlob = async () => {
    if (Platform.OS !== 'web') return null;
    const readyUrl = pdfUrl || await loadPdfPreview();
    if (!readyUrl) return null;
    const response = await fetch(readyUrl);
    return response.blob();
  };

  const trySavePdfInPreview = async () => {
    if (Platform.OS !== 'web') return;
    const blob = await getPdfBlob();
    if (!blob) {
      setActionNotice('PDF is not ready yet. Please try again.');
      return;
    }

    try {
      const result = await saveBlobWithBrowserFallback({ blob, filename: pdfFilename || defaultFilename });
      setActionNotice(result === 'saved' ? 'PDF saved successfully.' : result === 'shared' ? 'Share sheet opened for the PDF.' : 'PDF download started.');
      return;
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        setActionNotice('Save cancelled.');
        return;
      }
    }

    setActionNotice('App Preview blocked the PDF handoff. Use the manual link below.');
  };

  const handlePrint = async () => {
    if (Platform.OS === 'web') {
      if (isEmbeddedPreview) {
        setActionNotice('Trying to hand off the PDF to the browser…');
        window.setTimeout(() => window.location.assign(fileUrl), 150);
        return;
      }
      window.print();
      return;
    }
  };

  const handleDownload = async () => {
    if (Platform.OS === 'web') {
      if (isEmbeddedPreview) {
        setActionNotice('Trying to hand off the PDF to the browser…');
        window.setTimeout(() => window.location.assign(fileUrl), 150);
        return;
      }
      await downloadWebPdf();
      return;
    }
    await Linking.openURL(fileUrl);
  };

  const handleDownloadCsv = async () => {
    if (!paymentId) return;
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      await Linking.openURL(csvFileUrl);
      return;
    }
    const anchor = document.createElement('a');
    anchor.href = csvFileUrl;
    anchor.download = `${docType}-${String(doc?.payment_id || doc?.id || doc?.session_id || paymentId || 'payment')}-enterprise.csv`;
    anchor.target = '_blank';
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  };

  useEffect(() => {
    if (Platform.OS !== 'web' || !paymentId || loading || error) return;
    loadPdfPreview();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paymentId, loading, error, docType]);

  useEffect(() => {
    if (Platform.OS !== 'web' || isEmbeddedPreview || loading || !!error || action !== 'download' || !shouldAutoAction || autoActionStartedRef.current) return;

    autoActionStartedRef.current = true;
    setActionNotice('Preparing your PDF download…');
    const timer = window.setTimeout(() => {
      void handleDownload();
    }, 280);

    return () => window.clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, shouldAutoAction, isEmbeddedPreview, loading, error, paymentId, docType]);

  useEffect(() => () => {
    if (pdfUrl && typeof window !== 'undefined') {
      revokeObjectUrl(pdfUrl);
    }
  }, [pdfUrl]);

  if (loading) {
    return <AppShell><PaymentHistorySkeleton /></AppShell>;
  }

  if (error || !doc) {
    return (
      <AppShell>
        <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
          <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }}>
            <Text data-testid="payment-document-error" testID="payment-document-error" style={{ color: C.text, fontSize: 18, fontWeight: '700' }}>{error || 'Document unavailable'}</Text>
            <TouchableOpacity data-testid="payment-document-back-button" testID="payment-document-back-button" onPress={() => router.push('/payment-history' as any)} style={{ marginTop: 16, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999, backgroundColor: C.primary }}>
              <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("autofix.back.to.payment.history")}</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 40 }}>
          <View style={{ backgroundColor: C.card, borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: C.border, shadowColor: colors.card, shadowOpacity: 0.08, shadowOffset: { width: 0, height: 8 }, shadowRadius: 18, elevation: 3 }} data-testid="payment-document-page" testID="payment-document-page">
            <LinearGradient colors={[C.heroStart, C.heroMid, C.heroEnd]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={{ padding: 24 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <View style={{ alignSelf: 'flex-start' }}>
                  {Platform.OS === 'web'
                    ? React.createElement('img', {
                        src: brandLogoUrl,
                        alt: 'RealAICoach full logo',
                        'data-testid': 'payment-document-brand-logo',
                        style: { width: '132px', maxWidth: '100%', height: 'auto', display: 'block' },
                      })
                    : <Image source={require('../assets/images/brand-logo-chip.png')} style={{ width: 132, height: 42 }} resizeMode="contain" testID="payment-document-brand-logo" />}
                </View>
                <View style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.16)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.24)' }} data-testid="payment-document-meta-pill" testID="payment-document-meta-pill">
                  <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 }}>Billing Record</Text>
                  <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', marginTop: 4 }}>{dateLabel}</Text>
                </View>
              </View>
              <Text style={{ color: colors.primaryText, fontSize: 14, marginTop: 8 }}>Secure billing document</Text>
              <Text data-testid="payment-document-title" testID="payment-document-title" style={{ color: colors.primaryText, fontSize: 34, fontWeight: '800', marginTop: 12, letterSpacing: -0.6 }}>{docType === 'receipt' ? 'RECEIPT' : 'INVOICE'}</Text>
              <Text style={{ color: colors.primaryText, marginTop: 6 }}>{shortId}</Text>
              <Text data-testid="payment-document-date" testID="payment-document-date" style={{ color: colors.primaryText, marginTop: 6 }}>{dateLabel}</Text>
            </LinearGradient>

            <View style={{ padding: 24 }}>
              {isEmbeddedPreview && (
                <PreviewNoticeCard
                  backgroundColor={C.bgSoft}
                  borderColor={C.border}
                  message="This screen stays inside App Preview. Chrome blocks the inline PDF viewer here, so the document details stay visible on this page and the PDF actions below save the file directly."
                  messageColor={C.textMuted}
                  testId="payment-document-preview-banner"
                  title="Preview-safe document view"
                  titleColor={C.text}
                />
              )}

              {action === 'download' && (
                <PreviewNoticeCard
                  backgroundColor={colors.primarySoft}
                  borderColor={colors.primarySoft}
                  message={shouldAutoAction && !isEmbeddedPreview ? 'Your PDF download should begin automatically. If the browser blocks it, use the Download PDF button below.' : 'Use the Download PDF button below to continue.'}
                  messageColor={colors.primary}
                  testId="payment-document-download-banner"
                  title="Download requested"
                  titleColor={colors.primary}
                />
              )}

              <View style={{ marginBottom: 20, borderWidth: 1, borderColor: colors.border, borderRadius: 16, padding: 16, backgroundColor: colors.card }} data-testid="payment-document-customer-panel" testID="payment-document-customer-panel">
                <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700' }}>CUSTOMER</Text>
                <View style={{ flexDirection: 'row', gap: 16, flexWrap: 'wrap', marginTop: 12 }}>
                  <View style={{ minWidth: 140 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Name</Text><Text data-testid="payment-document-customer-name" testID="payment-document-customer-name" style={{ color: C.text, fontWeight: '700', marginTop: 6 }}>{user?.name || 'Customer'}</Text></View>
                  <View style={{ minWidth: 180 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Email</Text><Text data-testid="payment-document-customer-email" testID="payment-document-customer-email" style={{ color: C.text, fontWeight: '700', marginTop: 6 }}>{user?.email || ''}</Text></View>
                </View>
              </View>

              <View style={{ marginBottom: 20, borderWidth: 1, borderColor: colors.border, borderRadius: 16, padding: 16 }} data-testid="payment-document-line-items-panel" testID="payment-document-line-items-panel">
                <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700' }}>PAYMENT DETAILS</Text>
                <View style={{ marginTop: 12, borderTopWidth: 1, borderTopColor: C.border }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.border }}>
                    <BillingGlossaryLabel
                      accentColor={C.primary}
                      dataTestId="payment-document-base-price-glossary"
                      glossaryKey="subtotal"
                      label={`Base Subscription Price — ${planName} Plan (${String(doc?.billing_period || 'monthly')})`}
                      textColor={C.text}
                    />
                    <Text data-testid="payment-document-amount" testID="payment-document-amount" style={{ color: C.text, fontWeight: '700' }}>${subtotal.toFixed(2)}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.border }}>
                    <BillingGlossaryLabel
                      accentColor={C.primary}
                      dataTestId="payment-document-tax-glossary"
                      glossaryKey="applicable_tax"
                      label="Applicable Tax"
                      textColor={C.text}
                    />
                    <Text style={{ color: C.text, fontWeight: '700' }}>${taxAmount.toFixed(2)}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: C.border }}>
                    <BillingGlossaryLabel
                      accentColor={C.primary}
                      dataTestId="payment-document-processing-fee-glossary"
                      glossaryKey="processing_fee"
                      label="Payment Processing Fee"
                      textColor={C.text}
                    />
                    <Text style={{ color: C.text, fontWeight: '700' }}>${processingFee.toFixed(2)}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingTop: 16 }}>
                    <BillingGlossaryLabel
                      accentColor={C.primary}
                      dataTestId="payment-document-total-you-pay-glossary"
                      glossaryKey="total_you_pay"
                      label="Total You Pay"
                      textColor={colors.info}
                    />
                    <Text style={{ color: colors.info, fontSize: 24, fontWeight: '700' }}>${totalAmount.toFixed(2)} {String(doc?.currency || 'usd').toUpperCase()}</Text>
                  </View>
                </View>
              </View>

              {transparencyMode && (
                <View style={{ marginBottom: 20, borderWidth: 1, borderColor: colors.primarySoft, borderRadius: 16, padding: 16, backgroundColor: colors.primarySoft }} data-testid="payment-document-finance-glossary-panel" testID="payment-document-finance-glossary-panel">
                  <Text style={{ color: colors.primary, letterSpacing: 2, fontSize: 12, fontWeight: '700' }}>FINANCE GLOSSARY</Text>
                  <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 8 }}>Shown because receipt transparency mode is enabled.</Text>
                  <View style={{ marginTop: 12, gap: 10 }}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
                      <BillingGlossaryLabel
                        accentColor={C.primary}
                        dataTestId="payment-document-customer-charge-total-glossary"
                        glossaryKey="customer_charge_total"
                        label="Customer Charge Total"
                        textColor={C.text}
                      />
                      <Text style={{ color: C.text, fontWeight: '700' }} data-testid="payment-document-customer-charge-total" testID="payment-document-customer-charge-total">${totalAmount.toFixed(2)} {String(doc?.currency || 'usd').toUpperCase()}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
                      <BillingGlossaryLabel
                        accentColor={C.primary}
                        dataTestId="payment-document-net-settlement-glossary"
                        glossaryKey="net_settlement"
                        label="Net Settlement After Fee"
                        textColor={C.text}
                      />
                      <Text style={{ color: C.text, fontWeight: '700' }} data-testid="payment-document-net-settlement" testID="payment-document-net-settlement">${netSettlement.toFixed(2)} {String(doc?.currency || 'usd').toUpperCase()}</Text>
                    </View>
                  </View>
                </View>
              )}

              <View style={{ marginBottom: 20, borderWidth: 1, borderColor: colors.border, borderRadius: 16, padding: 16, backgroundColor: colors.card }} data-testid="payment-document-info-panel" testID="payment-document-info-panel">
                <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700' }}>PAYMENT INFO</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16, marginTop: 12 }}>
                  <View style={{ minWidth: 140 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Method</Text><Text data-testid="payment-document-method" testID="payment-document-method" style={{ color: C.text, fontWeight: '700', marginTop: 6 }}>{paymentMethod}</Text></View>
                  <View style={{ minWidth: 140 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Status</Text><Text data-testid="payment-document-status" testID="payment-document-status" style={{ color: statusLabel.toLowerCase() === 'paid' ? C.success : colors.warning, fontWeight: '700', marginTop: 6 }}>{statusLabel}</Text></View>
                  <View style={{ minWidth: 140 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Transaction ID</Text><Text data-testid="payment-document-transaction-id" testID="payment-document-transaction-id" style={{ color: C.text, fontWeight: '700', marginTop: 6 }}>{String(doc?.payment_id || doc?.id || doc?.session_id || paymentId)}</Text></View>
                  <View style={{ minWidth: 140 }}><Text style={{ color: C.textMuted, fontSize: 12 }}>Date</Text><Text style={{ color: C.text, fontWeight: '700', marginTop: 6 }}>{dateLabel}</Text></View>
                </View>
              </View>

              {Platform.OS === 'web' && (
                <View style={{ marginTop: 6 }} data-testid="payment-document-pdf-preview" testID="payment-document-pdf-preview">
                  <Text style={{ color: C.textMuted, letterSpacing: 2, fontSize: 12, fontWeight: '700', marginBottom: 12 }}>{isEmbeddedPreview ? 'PDF FILE STATUS' : 'DOCUMENT PREVIEW'}</Text>
                  {pdfLoading && (
                    <PaymentHistorySkeleton />
                  )}
                  {!pdfLoading && !pdfUrl && (
                    <View style={{ minHeight: 140, borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 20, alignItems: 'center', justifyContent: 'center' }} data-testid="payment-document-pdf-error" testID="payment-document-pdf-error">
                      <Text style={{ color: C.text, fontWeight: '700', textAlign: 'center' }}>{pdfError || 'The PDF file is not ready yet.'}</Text>
                      <Text style={{ color: C.textMuted, textAlign: 'center', marginTop: 8 }}>Try the Download PDF button below.</Text>
                    </View>
                  )}
                  {!pdfLoading && !!pdfUrl && (
                    <PdfCanvasPreview
                      accentColor={C.primary}
                      backgroundColor={C.bgSoft}
                      borderColor={C.border}
                      directUrl={fileUrl}
                      documentId={paymentId}
                      emptyMessage="Waiting for PDF data..."
                      errorMessage="Unable to render the PDF inline."
                      mutedColor={C.textMuted}
                      pdfUrl={pdfUrl}
                      testIdPrefix="payment-document-pdf-canvas"
                      textColor={C.text}
                      title=""
                    />
                  )}
                </View>
              )}
            </View>

            <View style={{ padding: 24, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.bgSoft }}>
              <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
                {Platform.OS === 'web' ? (
                  <>
                    {isEmbeddedPreview ? (
                      <>
                        <button
                          type="button"
                          data-testid="payment-document-print-button"
                          onClick={() => { void trySavePdfInPreview(); }}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: 'linear-gradient(135deg, #0F766E, #4F46E5)', border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 22px rgba(37,99,235,0.28)' }}
                        >
                          Save PDF
                        </button>
                        <button
                          type="button"
                          data-testid="payment-document-download-button"
                          onClick={selectManualPdfLink}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: 'linear-gradient(135deg, #4F46E5, #0891B2)', border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 22px rgba(79,70,229,0.25)' }}
                        >
                          Select Download Link
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          data-testid="payment-document-print-button"
                          onClick={() => { void handlePrint(); }}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: 'linear-gradient(135deg, #0F766E, #4F46E5)', border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 22px rgba(37,99,235,0.28)' }}
                        >
                          Print / Save as PDF
                        </button>
                        <button
                          type="button"
                          data-testid="payment-document-download-button"
                          onClick={() => { void handleDownload(); }}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: 'linear-gradient(135deg, #4F46E5, #0891B2)', border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 22px rgba(79,70,229,0.25)' }}
                        >{t("autofix.download.pdf")}</button>
                        <button
                          type="button"
                          data-testid="payment-document-download-csv-button"
                          onClick={() => { void handleDownloadCsv(); }}
                          style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, background: 'linear-gradient(135deg, #0F766E, #14B8A6)', border: 'none', color: colors.primaryText, fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 22px rgba(20,184,166,0.28)' }}
                        >{t("autofix.download.csv")}</button>
                      </>
                    )}
                    <button
                      type="button"
                      data-testid="payment-document-back-button"
                      onClick={() => router.push('/payment-history' as any)}
                      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, backgroundColor: C.bgSoft, border: `1px solid ${C.border}`, color: C.text, fontWeight: 700, cursor: 'pointer' }}
                    >{t("autofix.back.to.payment.history")}</button>
                    {isEmbeddedPreview && (
                      <button
                        type="button"
                        data-testid="payment-document-copy-link-button"
                        onClick={() => { void copyPdfLink(); }}
                        style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '12px 18px', borderRadius: 999, backgroundColor: 'transparent', border: `1px dashed ${C.border}`, color: C.textMuted, fontWeight: 700, cursor: 'pointer' }}
                      >{t("autofix.copy.pdf.link")}</button>
                    )}
                  </>
                ) : (
                  <>
                    <TouchableOpacity data-testid="payment-document-print-button" testID="payment-document-print-button" onPress={() => { void handlePrint(); }} style={{ backgroundColor: C.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{isEmbeddedPreview ? 'Save Document PDF' : 'Print / Save as PDF'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity data-testid="payment-document-download-button" testID="payment-document-download-button" onPress={() => { void handleDownload(); }} style={{ backgroundColor: colors.indigo, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("autofix.download.pdf")}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity data-testid="payment-document-download-csv-button" testID="payment-document-download-csv-button" onPress={() => { void handleDownloadCsv(); }} style={{ backgroundColor: colors.success, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("autofix.download.csv")}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity data-testid="payment-document-back-button" testID="payment-document-back-button" onPress={() => router.push('/payment-history' as any)} style={{ backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                      <Text style={{ color: C.text, fontWeight: '700' }}>{t("autofix.back.to.payment.history")}</Text>
                    </TouchableOpacity>
                    {isEmbeddedPreview && (
                      <TouchableOpacity data-testid="payment-document-copy-link-button" testID="payment-document-copy-link-button" onPress={() => { void copyPdfLink(); }} style={{ backgroundColor: 'transparent', borderWidth: 1, borderStyle: 'dashed', borderColor: C.border, paddingHorizontal: 18, paddingVertical: 12, borderRadius: 999 }}>
                        <Text style={{ color: C.textMuted, fontWeight: '700' }}>{t("autofix.copy.pdf.link")}</Text>
                      </TouchableOpacity>
                    )}
                  </>
                )}
              </View>
              {!!actionNotice && <InlineNotice backgroundColor={C.card} borderColor={C.border} message={actionNotice} testId="payment-document-action-notice" textColor={C.text} />}
              {isEmbeddedPreview && (
                <ManualLinkPanel
                  backgroundColor={C.card}
                  borderColor={C.border}
                  inputRef={(node: any) => { manualLinkInputRef.current = node; }}
                  inputTestId="payment-document-manual-link-input"
                  label="Manual PDF Link"
                  panelTestId="payment-document-manual-link-panel"
                  textColor={C.text}
                  value={fileUrl}
                />
              )}
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}