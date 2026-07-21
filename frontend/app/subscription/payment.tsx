import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import { useAccessControl } from '../../src/context/AccessControlContext';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/services/api';
import { fetchSubscriptionGatewayConfig, resolvePaymentMethodsFromGatewayConfig } from '../../src/services/subscriptionPaymentMethods';
import { useTheme } from '../../src/context/ThemeContext';
import { HeartbeatPulse } from '../../src/components/common/HeartbeatPulse';
import { EnterprisePaymentSummary } from '../../src/components/payment/EnterprisePaymentSummary';
import { PaymentMethodSelector } from '../../src/components/payment/PaymentMethodSelector';
import { SecurePaymentAssurancePanel } from '../../src/components/payment/SecurePaymentAssurancePanel';
import { SubscriptionSuccessPanel } from '../../src/components/payment/SubscriptionSuccessPanel';
import { SubscriptionUnlockedDestinationSummary } from '../../src/components/payment/SubscriptionUnlockedDestinationSummary';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useViewportWidth } from '../../src/hooks/useViewportWidth';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { normalizeReturnTarget } from '../../src/utils/subscriptionReturnTarget';
import { stashSubscriptionReturnToast } from '../../src/utils/subscriptionReturnToast';
import { getPaymentFailureCopy } from '../../src/utils/paymentFailureCopy';

type SavedCard = {
  card_id: string;
  card_type: string;
  last_four: string;
  expiry_month: number;
  expiry_year: number;
  is_default?: boolean;
  validity_status?: string;
};

const PAYMENT_PENDING_RESUME_URL_KEY = 'payment_pending_resume_url';
const PAYMENT_PENDING_RESUME_EXPIRY_KEY = 'payment_pending_resume_expiry_at';
const PAYMENT_PENDING_RESUME_METHOD_KEY = 'payment_pending_resume_method';
const PAYMENT_PENDING_RESUME_TTL_MS = 30 * 60 * 1000;

export default function PaymentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const { refreshUser, user } = useAuth();
  const { refresh: refreshAccessControl } = useAccessControl();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const viewportWidth = useViewportWidth();
  // Use state to track if we're on client-side to avoid SSR hydration mismatch
  const [isClient, setIsClient] = useState(false);
  useEffect(() => {
    setIsClient(true);
    console.log('[PaymentScreen] isClient set to true, viewportWidth:', viewportWidth);
  }, []);
  const isVerySmallPhone = isClient && viewportWidth <= 390;
  console.log('[PaymentScreen] isClient:', isClient, 'viewportWidth:', viewportWidth, 'isVerySmallPhone:', isVerySmallPhone);
  const [compactMode, setCompactMode] = useState(isVerySmallPhone);
  const [compactModeTouched, setCompactModeTouched] = useState(false);
  const isCompact = (viewportWidth < 420 && !isVerySmallPhone) || (isVerySmallPhone && compactMode);
  const isTablet = viewportWidth >= 768;

  // @autofix-moved: was module-level const createStyles
  const createStyles = (COLORS: any, compact: boolean, tablet: boolean) => StyleSheet.create({
    container: {
      flex: 1,
      backgroundColor: COLORS.background,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: compact ? 12 : 16,
      paddingVertical: 12,
      borderBottomWidth: 1,
      borderBottomColor: COLORS.border,
    },
    backButton: {
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: COLORS.backgroundSecondary,
      alignItems: 'center',
      justifyContent: 'center',
    },
    headerTitle: {
      fontSize: compact ? 16 : 18,
      fontWeight: '700',
      color: COLORS.text,
    },
    headerSpacer: {
      width: 40,
    },
    scrollContent: {
      padding: compact ? 12 : 16,
      paddingBottom: 24,
      width: '100%',
      alignSelf: 'center',
      maxWidth: tablet ? 860 : 680,
    },
    // Summary Card
    summaryCard: {
      backgroundColor: (globalThis as any).__alphaColor(COLORS.premium, '10'),
      borderRadius: 16,
      padding: 16,
      marginBottom: 20,
      borderWidth: 1,
      borderColor: (globalThis as any).__alphaColor(COLORS.premium, '30'),
    },
    summaryTitle: {
      fontSize: 14,
      fontWeight: '600',
      color: COLORS.textSecondary,
      marginBottom: 12,
    },
    summaryRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: compact ? 'flex-start' : 'center',
      flexWrap: compact ? 'wrap' : 'nowrap',
      rowGap: compact ? 8 : 0,
    },
    summaryPlan: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 12,
      flex: 1,
      minWidth: 0,
    },
    planIconBox: {
      width: 44,
      height: 44,
      borderRadius: 12,
      backgroundColor: (globalThis as any).__alphaColor(COLORS.premium, '20'),
      alignItems: 'center',
      justifyContent: 'center',
    },
    planNameText: {
      fontSize: compact ? 14 : 16,
      fontWeight: '700',
      color: COLORS.text,
      flexShrink: 1,
    },
    planPeriodText: {
      fontSize: compact ? 12 : 13,
      color: COLORS.textSecondary,
      marginTop: 2,
    },
    planPriceText: {
      fontSize: compact ? 16 : 18,
      fontWeight: '700',
      color: COLORS.premium,
      textAlign: 'right',
      marginLeft: compact ? 56 : 0,
    },
    summaryDivider: {
      height: 1,
      backgroundColor: COLORS.border,
      marginVertical: 12,
    },
    totalRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    totalLabel: {
      fontSize: compact ? 14 : 16,
      fontWeight: '600',
      color: COLORS.text,
    },
    totalPrice: {
      fontSize: compact ? 18 : 20,
      fontWeight: '700',
      color: COLORS.text,
      textAlign: 'right',
    },
    // Section
    section: {
      marginBottom: 20,
    },
    sectionTitle: {
      fontSize: 16,
      fontWeight: '700',
      color: COLORS.text,
      marginBottom: 12,
    },
    // Payment Methods
    paymentMethods: {
      gap: 12,
    },
    paymentOption: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: COLORS.surface,
      borderRadius: 12,
      padding: 16,
      borderWidth: 1.5,
      borderColor: COLORS.border,
      gap: 12,
    },
    paymentOptionActive: {
      borderColor: COLORS.primary,
      backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '05'),
    },
    paymentOptionContent: {
      flex: 1,
    },
    paymentOptionText: {
      fontSize: 15,
      color: COLORS.textSecondary,
      fontWeight: '500',
    },
    paymentOptionTextActive: {
      color: COLORS.text,
      fontWeight: '600',
    },
    paymentOptionSubtext: {
      fontSize: 12,
      color: COLORS.textMuted,
      marginTop: 2,
    },
    // Card Inputs
    inputGroup: {
      marginBottom: 16,
    },
    inputLabel: {
      fontSize: 13,
      fontWeight: '600',
      color: COLORS.textSecondary,
      marginBottom: 8,
    },
    inputContainer: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: COLORS.backgroundSecondary,
      borderRadius: 12,
      paddingHorizontal: 14,
      borderWidth: 1,
      borderColor: COLORS.border,
    },
    textInput: {
      flex: 1,
      paddingVertical: 14,
      marginLeft: 10,
      fontSize: 15,
      color: COLORS.text,
    },
    rowInputs: {
      flexDirection: 'row',
    },
    cardNoteBox: {
      flexDirection: 'row',
      alignItems: 'center',
      backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '08'),
      borderRadius: 8,
      padding: 10,
      gap: 8,
    },
    cardNoteText: {
      flex: 1,
      fontSize: 12,
      color: COLORS.textSecondary,
      lineHeight: 16,
    },
    // PayPal Info
    paypalInfo: {
      alignItems: 'center',
      padding: compact ? 16 : 24,
      backgroundColor: COLORS.backgroundSecondary,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: COLORS.border,
    },
    paypalIconContainer: {
      width: 72,
      height: 72,
      borderRadius: 36,
      backgroundColor: (globalThis as any).__alphaColor(COLORS.paypal, '10'),
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 16,
    },
    paypalTitle: {
      fontSize: compact ? 16 : 18,
      fontWeight: '700',
      color: COLORS.text,
      marginBottom: 8,
      textAlign: 'center',
    },
    paypalText: {
      fontSize: 14,
      color: COLORS.textSecondary,
      textAlign: 'center',
      lineHeight: 20,
      marginBottom: 16,
    },
    paypalFeatures: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      justifyContent: 'center',
      gap: compact ? 10 : 16,
    },
    paypalFeatureItem: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    paypalFeatureText: {
      fontSize: 12,
      color: COLORS.textSecondary,
      fontWeight: '500',
    },
    // Security Note
    securityNote: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      backgroundColor: (globalThis as any).__alphaColor(COLORS.success, '10'),
      borderRadius: 12,
      padding: 14,
      marginBottom: 20,
      gap: 10,
    },
    securityText: {
      flex: 1,
      fontSize: 13,
      color: COLORS.textSecondary,
      lineHeight: 18,
    },
    // Pay Button
    payButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: COLORS.primary,
      borderRadius: 14,
      paddingVertical: 18,
      paddingHorizontal: compact ? 10 : 16,
      gap: 10,
    },
    paypalButton: {
      backgroundColor: COLORS.paypalLight,
    },
    payButtonDisabled: {
      opacity: 0.6,
    },
    payButtonText: {
      fontSize: compact ? 14 : 17,
      fontWeight: '700',
      color: colors.primaryText,
      flexShrink: 1,
      textAlign: 'center',
    },
    // Terms
    termsText: {
      fontSize: compact ? 11 : 12,
      color: COLORS.textMuted,
      textAlign: 'center',
      marginTop: 16,
      lineHeight: 18,
    },
    spacer: {
      height: 40,
    },
    // Success Screen
    successContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: compact ? 18 : 32,
      width: '100%',
    },
    successIconContainer: {
      marginBottom: 24,
    },
    successTitle: {
      fontSize: compact ? 20 : 24,
      fontWeight: '700',
      color: COLORS.text,
      marginBottom: 12,
      textAlign: 'center',
    },
    successSubtitle: {
      fontSize: compact ? 14 : 16,
      color: COLORS.textSecondary,
      textAlign: 'center',
      lineHeight: 24,
      marginBottom: 32,
    },
    successButton: {
      backgroundColor: COLORS.primary,
      paddingHorizontal: compact ? 18 : 40,
      paddingVertical: 16,
      borderRadius: 14,
      width: compact ? '100%' : undefined,
      alignItems: 'center',
    },
    successButtonText: {
      fontSize: compact ? 15 : 17,
      fontWeight: '700',
      color: colors.primaryText,
      textAlign: 'center',
    },
    // Processing Screen
    processingContainer: {
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      padding: compact ? 18 : 32,
    },
    processingTitle: {
      fontSize: compact ? 18 : 20,
      fontWeight: '700',
      color: COLORS.text,
      marginTop: 24,
      marginBottom: 12,
      textAlign: 'center',
    },
    processingSubtitle: {
      fontSize: compact ? 13 : 15,
      color: COLORS.textSecondary,
      textAlign: 'center',
      lineHeight: 22,
    },
  });
  
  const planId = String(params.planId || 'basic');
  const planName = String(params.planName || 'Basic');
  const planPriceParam = String(params.planPrice || '').trim();
  const billingPeriod = String(params.billingPeriod || 'monthly');
  const checkoutCurrency = String(params.currency || 'usd').toLowerCase();
  const returnTo = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);

  const initialPaymentMethod = String(params.paymentMethod || '').toLowerCase();
  const isAdmin = Boolean(user?.is_admin);
  const [paymentMethod, setPaymentMethod] = useState<'card' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap'>(
    // Store compliance: native builds default (and are limited) to platform IAP.
    Platform.OS === 'ios'
      ? 'apple_iap'
      : Platform.OS === 'android'
        ? 'google_iap'
        : initialPaymentMethod === 'paypal'
          ? 'paypal'
          : initialPaymentMethod === 'fedapay'
            ? 'fedapay'
            : initialPaymentMethod === 'apple_iap'
              ? 'apple_iap'
              : initialPaymentMethod === 'google_iap'
                ? 'google_iap'
                : 'card'
  );
  const [processing, setProcessing] = useState(false);
  const [paymentStep, setPaymentStep] = useState<'form' | 'processing' | 'success'>('form');
  const [checkoutPreview, setCheckoutPreview] = useState<any>(null);
  const [checkoutPreviewLoading, setCheckoutPreviewLoading] = useState(false);
  const [checkoutPreviewError, setCheckoutPreviewError] = useState('');
  type GatewayHealth = { status: 'loading' | 'healthy' | 'degraded' | 'unavailable'; message: string; mode: string };
  const [stripeHealth, setStripeHealth] = useState<GatewayHealth>({ status: 'loading', message: 'Checking Stripe gateway status...', mode: 'unknown' });
  const [paymentStatusCheckedAt, setPaymentStatusCheckedAt] = useState(Date.now());
  const [paymentStatusHeartbeatSec, setPaymentStatusHeartbeatSec] = useState(0);
  const [paypalHealth, setPaypalHealth] = useState<{
    status: 'loading' | 'healthy' | 'degraded' | 'unavailable';
    message: string;
    mode: string;
  }>({ status: 'loading', message: 'Checking PayPal gateway status...', mode: 'unknown' });
  const [fedapayHealth, setFedapayHealth] = useState<GatewayHealth>({ status: 'loading', message: 'Checking FedaPay gateway status...', mode: 'unknown' });
  const [appleIapHealth, setAppleIapHealth] = useState<GatewayHealth>({ status: 'loading', message: 'Checking Apple IAP status...', mode: 'unknown' });
  const [googleIapHealth, setGoogleIapHealth] = useState<GatewayHealth>({ status: 'loading', message: 'Checking Google IAP status...', mode: 'unknown' });
  const [methodAvailability, setMethodAvailability] = useState(() => resolvePaymentMethodsFromGatewayConfig(null));
  const [emailServiceAvailable, setEmailServiceAvailable] = useState<boolean | null>(null);
  const [savedCards, setSavedCards] = useState<SavedCard[]>([]);
  const [selectedCardId, setSelectedCardId] = useState('');
  const [canonicalPlanPrice, setCanonicalPlanPrice] = useState<number | null>(null);
  const [priceGuardLoading, setPriceGuardLoading] = useState(true);
  const [priceGuardError, setPriceGuardError] = useState('');
  const [priceGuardWarning, setPriceGuardWarning] = useState('');
  const [priceGuardAutocorrected, setPriceGuardAutocorrected] = useState(false);

  // Resume pending checkout CTA state
  const [pendingResumeUrl, setPendingResumeUrl] = useState('');
  const [pendingResumeMeta, setPendingResumeMeta] = useState('');
  const [pendingResumeExpiryAt, setPendingResumeExpiryAt] = useState<number | null>(null);
  const [pendingResumeMethod, setPendingResumeMethod] = useState('');
  const [resumeNowTs, setResumeNowTs] = useState<number>(Date.now());

  useEffect(() => {
    if (!isVerySmallPhone) {
      setCompactMode(false);
      setCompactModeTouched(false);
      return;
    }
    if (!compactModeTouched) {
      setCompactMode(true);
    }
  }, [compactModeTouched, isVerySmallPhone, isClient]);

  // Load persisted pending checkout on mount (web only)
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    try {
      const url = window.localStorage.getItem(PAYMENT_PENDING_RESUME_URL_KEY) || '';
      const expiryRaw = window.localStorage.getItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY) || '';
      const method = window.localStorage.getItem(PAYMENT_PENDING_RESUME_METHOD_KEY) || '';
      const expiry = Number(expiryRaw);
      if (url && Number.isFinite(expiry) && expiry > Date.now()) {
        setPendingResumeUrl(url);
        setPendingResumeExpiryAt(expiry);
        setPendingResumeMethod(method);
        setPendingResumeMeta(`Pending ${method === 'paypal' ? 'PayPal' : 'Stripe'} checkout available to resume.`);
      } else if (url) {
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_URL_KEY);
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY);
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_METHOD_KEY);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tick every second for live countdown
  useEffect(() => {
    if (!pendingResumeUrl || !pendingResumeExpiryAt) return;
    const id = setInterval(() => setResumeNowTs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [pendingResumeExpiryAt, pendingResumeUrl]);

  // Auto-clear when TTL expires
  useEffect(() => {
    if (!pendingResumeUrl || !pendingResumeExpiryAt) return;
    if (pendingResumeExpiryAt <= resumeNowTs) {
      setPendingResumeUrl('');
      setPendingResumeMeta('');
      setPendingResumeExpiryAt(null);
      setPendingResumeMethod('');
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        try {
          window.localStorage.removeItem(PAYMENT_PENDING_RESUME_URL_KEY);
          window.localStorage.removeItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY);
          window.localStorage.removeItem(PAYMENT_PENDING_RESUME_METHOD_KEY);
        } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
    }
  }, [pendingResumeExpiryAt, pendingResumeUrl, resumeNowTs]);

  const selectedSavedCard = useMemo(
    () => savedCards.find((card) => card.card_id === selectedCardId) || null,
    [savedCards, selectedCardId]
  );

  const COLORS = useMemo(() => ({
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    premium: colors.primary,
    paypal: colors.info || colors.primary,
    paypalLight: colors.primarySoft,
    successText: colors.successText,
    warningText: colors.warningText,
    errorText: colors.errorText,
    successSoft: colors.successSoft,
    warningSoft: colors.warningSoft,
    errorSoft: colors.errorSoft,
    info: colors.info,
    primarySoft: colors.primarySoft,
    primary: colors.primary,
    primaryDark: colors.primary,
    background: colors.bg,
    backgroundSecondary: colors.bgSoft,
    surface: colors.card,
    text: colors.text,
    textSecondary: colors.textSec,
    textMuted: colors.textMuted,
    border: colors.border,
  }), [colors]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const styles = useMemo(() => createStyles(COLORS, isCompact, isTablet), [COLORS, isCompact, isTablet]);
  const selectedGatewayHealth = paymentMethod === 'paypal'
    ? paypalHealth
    : paymentMethod === 'fedapay'
      ? fedapayHealth
      : paymentMethod === 'apple_iap'
        ? appleIapHealth
        : paymentMethod === 'google_iap'
          ? googleIapHealth
          : stripeHealth;
  const selectedGatewayLabel = paymentMethod === 'paypal'
    ? 'PayPal'
    : paymentMethod === 'fedapay'
      ? 'FedaPay'
      : paymentMethod === 'apple_iap'
        ? 'Apple IAP'
        : paymentMethod === 'google_iap'
          ? 'Google IAP'
          : 'Stripe';
  const selectedGatewaySlug = paymentMethod === 'paypal'
    ? 'paypal'
    : paymentMethod === 'fedapay'
      ? 'fedapay'
      : paymentMethod === 'apple_iap'
        ? 'apple_iap'
        : paymentMethod === 'google_iap'
          ? 'google_iap'
          : 'stripe';

  const paymentMethodOptions = useMemo(() => ([
    {
      id: 'stripe' as const,
      title: t('payment.method.card', 'Stripe'),
      subtitle: t('payment.method.cardSubtext', 'Visa, Mastercard, Amex'),
      iconName: 'card' as const,
      iconColor: paymentMethod === 'card' ? COLORS.primary : COLORS.textMuted,
      iconBg: `${COLORS.primary}12`,
      testId: 'payment-method-card',
    },
    {
      id: 'paypal' as const,
      title: t('payment.method.paypal', 'PayPal'),
      subtitle: t('payment.method.paypalSubtext', 'Fast & secure checkout'),
      iconName: 'logo-paypal' as const,
      iconColor: paymentMethod === 'paypal' ? COLORS.paypal : COLORS.textMuted,
      iconBg: `${COLORS.paypal}15`,
      testId: 'payment-method-paypal',
    },
    {
      id: 'fedapay' as const,
      title: 'FedaPay',
      subtitle: 'FedaPay (West Africa)',
      iconName: 'cash-outline' as const,
      iconColor: paymentMethod === 'fedapay' ? COLORS.successText : COLORS.textMuted,
      iconBg: `${COLORS.success}15`,
      testId: 'payment-method-fedapay',
    },
    {
      id: 'apple_iap' as const,
      title: 'Apple IAP',
      subtitle: 'App Store checkout handoff',
      iconName: 'logo-apple' as const,
      iconColor: paymentMethod === 'apple_iap' ? COLORS.primary : COLORS.textMuted,
      iconBg: `${COLORS.primary}15`,
      testId: 'payment-method-apple-iap',
    },
    {
      id: 'google_iap' as const,
      title: 'Google IAP',
      subtitle: 'Google Play checkout handoff',
      iconName: 'logo-google-playstore' as const,
      iconColor: paymentMethod === 'google_iap' ? COLORS.primary : COLORS.textMuted,
      iconBg: `${COLORS.primary}15`,
      testId: 'payment-method-google-iap',
    },
  ]), [COLORS.paypal, COLORS.primary, COLORS.success, COLORS.successText, COLORS.textMuted, paymentMethod, t]);

  // Store compliance (App Store 3.1.1 / Play Payments policy): on native builds,
  // digital-goods checkout must use the platform's IAP only. Web keeps all providers.
  const visiblePaymentMethodOptions = useMemo(() => {
    if (Platform.OS === 'web') return paymentMethodOptions;
    const nativeMethodId = Platform.OS === 'ios' ? 'apple_iap' : 'google_iap';
    return paymentMethodOptions.filter((option) => option.id === nativeMethodId);
  }, [paymentMethodOptions]);

  const selectedHealthTone = useMemo(() => {
    if (selectedGatewayHealth.status === 'healthy') return { color: COLORS.successText, bg: `${COLORS.success}22`, border: colors.successSoft, icon: 'checkmark-circle' };
    if (selectedGatewayHealth.status === 'unavailable') return { color: COLORS.error, bg: `${COLORS.error}22`, border: colors.errorSoft, icon: 'close-circle' };
    if (selectedGatewayHealth.status === 'degraded') return { color: COLORS.warningText, bg: `${COLORS.warning}22`, border: colors.warningSoft, icon: 'warning' };
    return { color: colors.info, bg: `${(colors.info || COLORS.primary)}22`, border: colors.primarySoft, icon: 'sync' };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedGatewayHealth.status, COLORS.error, COLORS.success, COLORS.warning]);

  const formatPreviewAmount = (value: any) => {
    const numeric = Number(value || 0);
    return Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00';
  };

  const feeText = useMemo(() => {
    return {
      title: tx('fees.explainer.title', 'Why these fees?'),
      line1: tx('fees.explainer.line1', 'Base Subscription Price: the plan amount before taxes and payment handling fees.'),
      line2: tx('fees.explainer.line2', 'Applicable Tax: calculated from your checkout jurisdiction and provider policy.'),
      line3: tx('fees.explainer.line3', 'Payment Processing Fee: charged by the payment/store channel for handling the transaction.'),
      line4: tx('fees.explainer.line4', 'Total You Pay: Base Subscription Price + Applicable Tax + Payment Processing Fee.'),
    };
  }, [tx]);

  const browserLocaleSignals = useMemo(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      return { preferredLanguage: '', browserLanguage: '', browserLanguages: '', region: '' };
    }
    const locale = Intl.DateTimeFormat().resolvedOptions().locale || navigator.language || '';
    const region = locale.includes('-') ? locale.split('-')[1]?.toUpperCase() || '' : '';
    return {
      preferredLanguage: (navigator.language || locale || '').split('-')[0]?.toLowerCase() || '',
      browserLanguage: navigator.language || locale || '',
      browserLanguages: Array.isArray(navigator.languages) ? navigator.languages.join(',') : (navigator.language || ''),
      region,
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadPaymentGatewayHealth = async () => {
      try {
        const data = await fetchSubscriptionGatewayConfig();
        if (!mounted) return;

        const available = resolvePaymentMethodsFromGatewayConfig(data);
        setMethodAvailability(available);

        const stripeAvailable = available.stripe.available;
        const stripeLabel = String(data?.stripe_status_label || (String(data?.stripe_mode || '').toLowerCase() === 'live' ? 'Live Ready' : 'Test Ready'));
        setEmailServiceAvailable(Boolean(data?.email_service_available));
        setStripeHealth({
          status: stripeAvailable ? 'healthy' : 'unavailable',
          message: stripeAvailable
            ? `${stripeLabel} — gateway configured for card checkout.`
            : 'Stripe gateway is not configured. Contact admin before checkout.',
          mode: stripeLabel.toUpperCase(),
        });

        const isAvailable = available.paypal.available;
        const paypalLabel = String(data?.paypal_status_label || (String(data?.paypal_mode || '').toLowerCase() === 'live' ? 'Live Ready' : 'Sandbox Ready'));
        setPaypalHealth({
          status: isAvailable ? 'healthy' : 'unavailable',
          message: isAvailable
            ? `${paypalLabel} — gateway configured for checkout redirect.`
            : 'PayPal gateway is not configured. Contact admin before checkout.',
          mode: paypalLabel.toUpperCase(),
        });

        const fedapayAvailable = available.fedapay.available;
        setFedapayHealth({
          status: fedapayAvailable ? 'healthy' : 'unavailable',
          message: fedapayAvailable
            ? 'FedaPay gateway is active. Continue to FedaPay checkout flow.'
            : 'FedaPay gateway is not configured. Contact admin before FedaPay checkout.',
          mode: fedapayAvailable ? 'ACTIVE' : 'UNAVAILABLE',
        });

        const appleIapAvailable = available.apple_iap.available;
        const appleLabel = String(data?.apple_iap_status_label || 'Unavailable');
        setAppleIapHealth({
          status: appleIapAvailable ? 'healthy' : 'unavailable',
          message: appleIapAvailable
            ? `${appleLabel} — continue to App Store checkout handoff.`
            : 'Apple IAP is not configured for this environment.',
          mode: appleLabel.toUpperCase(),
        });

        const googleIapAvailable = available.google_iap.available;
        const googleLabel = String(data?.google_iap_status_label || 'Unavailable');
        setGoogleIapHealth({
          status: googleIapAvailable ? 'healthy' : 'unavailable',
          message: googleIapAvailable
            ? `${googleLabel} — continue to Google Play checkout handoff.`
            : 'Google IAP is not configured for this environment.',
          mode: googleLabel.toUpperCase(),
        });
      } catch (error) {
        handleAppRecoverableError({
          scope: 'subscription.payment.load-gateway-health',
          error,
          message: 'Unable to verify gateway health right now.',
          setError: setPaymentError,
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        if (!mounted) return;
        setEmailServiceAvailable(null);
        setMethodAvailability(resolvePaymentMethodsFromGatewayConfig(null));
        setStripeHealth({
          status: 'degraded',
          message: 'Unable to verify Stripe configuration. Stripe checkout may still work.',
          mode: 'UNKNOWN',
        });
        setPaypalHealth({
          status: 'degraded',
          message: 'Unable to verify PayPal configuration. Redirect checkout may still work.',
          mode: 'UNKNOWN',
        });
        setFedapayHealth({
          status: 'degraded',
          message: 'Unable to verify FedaPay configuration. FedaPay checkout status is unknown.',
          mode: 'UNKNOWN',
        });
        setAppleIapHealth({
          status: 'degraded',
          message: 'Unable to verify Apple IAP readiness at this time.',
          mode: 'UNKNOWN',
        });
        setGoogleIapHealth({
          status: 'degraded',
          message: 'Unable to verify Google IAP readiness at this time.',
          mode: 'UNKNOWN',
        });
      }
    };
    loadPaymentGatewayHealth();
    const intervalId = setInterval(loadPaymentGatewayHealth, 30000);
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadSavedCards = async () => {
      try {
        const { data } = await api.get('/payments/cards/checkout-ready');
        if (!mounted) return;
        const cards: SavedCard[] = data?.cards || [];
        setSavedCards(cards);
        if (cards.length === 0) {
          setSelectedCardId('');
          return;
        }
        const defaultCardId = data?.default_card?.card_id || cards.find((card) => card.is_default)?.card_id || cards[0]?.card_id;
        setSelectedCardId(defaultCardId || '');
      } catch (error) {
        handleAppRecoverableError({
          scope: 'subscription.payment.load-saved-cards',
          error,
          message: 'Could not load saved cards right now.',
          setError: setPaymentError,
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        if (!mounted) return;
        setSavedCards([]);
        setSelectedCardId('');
      }
    };
    loadSavedCards();
    return () => {
      mounted = false;
    };
  }, []);

  const emitPricingGuardEvent = useCallback(async (payload: any) => {
    try {
      await api.post('/subscriptions/pricing-guard/frontend-event', payload, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const emitCheckoutFrontendEvent = useCallback(async (payload: any) => {
    try {
      await api.post('/subscriptions/checkout/frontend-event', payload, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const clearPendingResume = useCallback(() => {
    setPendingResumeUrl('');
    setPendingResumeMeta('');
    setPendingResumeExpiryAt(null);
    setPendingResumeMethod('');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_URL_KEY);
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY);
        window.localStorage.removeItem(PAYMENT_PENDING_RESUME_METHOD_KEY);
      } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, []);

  const resumePendingCheckout = useCallback(() => {
    if (!pendingResumeUrl) return;
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.location.href = pendingResumeUrl;
      return;
    }
    Alert.alert('Resume Checkout', 'Open this checkout URL to continue your pending payment.');
  }, [pendingResumeUrl]);

  const resumeCountdownLabel = useMemo(() => {
    if (!pendingResumeExpiryAt) return '';
    const remaining = Math.max(0, pendingResumeExpiryAt - resumeNowTs);
    if (remaining === 0) return '';
    const mins = Math.floor(remaining / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
  }, [pendingResumeExpiryAt, resumeNowTs]);

  useEffect(() => {
    if (paymentStep === 'success') clearPendingResume();
  }, [paymentStep, clearPendingResume]);

  useEffect(() => {
    let mounted = true;
    const resolveCanonicalPlanPrice = async () => {
      setPriceGuardLoading(true);
      setPriceGuardError('');
      setPriceGuardWarning('');
      setPriceGuardAutocorrected(false);
      try {
        const { data } = await api.get(`/subscriptions/plans?currency=${checkoutCurrency.toUpperCase()}`, { silentLoading: true });
        if (!mounted) return;
        const plans = Array.isArray(data?.plans) ? data.plans : [];
        const selected = plans.find((plan: any) => String(plan?.id || '').toLowerCase() === String(planId || '').toLowerCase());
        if (!selected) {
          throw new Error('Selected plan is missing in platform catalog');
        }

        const canonical = Number(billingPeriod === 'monthly' ? selected?.monthly_price : selected?.yearly_price);
        if (!Number.isFinite(canonical) || canonical < 0) {
          throw new Error('Canonical plan price unavailable');
        }

        setCanonicalPlanPrice(canonical);

        const incomingPrice = Number(planPriceParam);
        const hasIncoming = planPriceParam.length > 0 && Number.isFinite(incomingPrice);
        const mismatch = hasIncoming && Math.abs(incomingPrice - canonical) > 0.01;
        if (mismatch) {
          setPriceGuardAutocorrected(true);
          emitPricingGuardEvent({
            event_type: 'param_mismatch_autocorrected',
            route: '/subscription/payment',
            plan_id: planId,
            billing_period: billingPeriod,
            payment_method: String(params.paymentMethod || paymentMethod || 'stripe'),
            currency: checkoutCurrency,
            param_price: incomingPrice,
            canonical_price: canonical,
            reason: 'Frontend query price mismatch; canonical catalog price applied',
          });
        }
      } catch (error: any) {
        if (!mounted) return;
        const incomingPrice = Number(planPriceParam);
        const hasIncoming = planPriceParam.length > 0 && Number.isFinite(incomingPrice) && incomingPrice > 0;
        if (hasIncoming) {
          setCanonicalPlanPrice(incomingPrice);
          setPriceGuardWarning('Live pricing source is temporarily unavailable. Checkout is using signed route snapshot pricing.');
          setPriceGuardError('');
          emitPricingGuardEvent({
            event_type: 'source_unavailable_degraded_safe',
            route: '/subscription/payment',
            plan_id: planId,
            billing_period: billingPeriod,
            payment_method: String(params.paymentMethod || paymentMethod || 'stripe'),
            currency: checkoutCurrency,
            param_price: incomingPrice,
            canonical_price: incomingPrice,
            reason: String(error?.message || 'source unavailable; degraded-safe fallback applied'),
          });
        } else {
          setCanonicalPlanPrice(null);
          setPriceGuardError('Live platform pricing is temporarily unavailable. Checkout is locked to prevent price mismatch.');
          emitPricingGuardEvent({
            event_type: 'source_unavailable_blocked',
            route: '/subscription/payment',
            plan_id: planId,
            billing_period: billingPeriod,
            payment_method: String(params.paymentMethod || paymentMethod || 'stripe'),
            currency: checkoutCurrency,
            param_price: Number(planPriceParam || 0),
            canonical_price: null,
            reason: String(error?.message || 'source unavailable'),
          });
        }
      } finally {
        if (mounted) setPriceGuardLoading(false);
      }
    };

    resolveCanonicalPlanPrice();
    return () => {
      mounted = false;
    };
  }, [billingPeriod, checkoutCurrency, emitPricingGuardEvent, params.paymentMethod, planId, planPriceParam]);

  useEffect(() => {
    setPaymentStatusCheckedAt(Date.now());
  }, [paymentMethod, selectedGatewayHealth.status, selectedGatewayHealth.message, selectedGatewayHealth.mode]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setPaymentStatusHeartbeatSec(Math.max(0, Math.floor((Date.now() - paymentStatusCheckedAt) / 1000)));
    }, 1000);
    return () => clearInterval(intervalId);
  }, [paymentStatusCheckedAt]);

  useEffect(() => {
    let mounted = true;
    const loadCheckoutPreview = async () => {
      if (!planId) return;
      setCheckoutPreviewLoading(true);
      setCheckoutPreviewError('');
      try {
        const method = paymentMethod === 'paypal'
          ? 'paypal'
          : paymentMethod === 'fedapay'
            ? 'fedapay'
            : paymentMethod === 'apple_iap' || paymentMethod === 'google_iap'
              ? 'stripe'
              : 'stripe';
        const { data } = await api.post('/subscriptions/checkout-preview', {
          plan_id: planId,
          billing_period: billingPeriod,
          payment_method: method,
          currency: checkoutCurrency,
          country_code: browserLocaleSignals.region || undefined,
          preferred_language: browserLocaleSignals.preferredLanguage || undefined,
          browser_language: browserLocaleSignals.browserLanguage || undefined,
          browser_languages: browserLocaleSignals.browserLanguages || undefined,
        });
        if (!mounted) return;
        setCheckoutPreview(data || null);
      } catch (e: any) {
        if (!mounted) return;
        setCheckoutPreviewError(e?.response?.data?.detail || 'Unable to load fee breakdown.');
      } finally {
        if (mounted) setCheckoutPreviewLoading(false);
      }
    };
    loadCheckoutPreview();
    return () => { mounted = false; };
  }, [planId, billingPeriod, paymentMethod, checkoutCurrency, browserLocaleSignals]);

  const feePreviewBlocking = checkoutPreviewLoading || !checkoutPreview || Boolean(checkoutPreviewError);
  const previewBlockingForCurrentMethod = paymentMethod === 'fedapay' && feePreviewBlocking;
  const effectivePlanPrice = Number.isFinite(Number(canonicalPlanPrice)) ? Number(canonicalPlanPrice) : Number(planPriceParam || 0);
  const submitDisabled = processing || previewBlockingForCurrentMethod || priceGuardLoading || Boolean(priceGuardError);
  const submitDisableReason = priceGuardError
    ? priceGuardError
    : previewBlockingForCurrentMethod
      ? 'Live fee preview is still loading for FedaPay. Please wait a moment.'
      : priceGuardLoading
        ? 'Validating live platform pricing before checkout...'
        : '';

  const providerKeyForSummary = paymentMethod === 'card' ? 'stripe' : paymentMethod;
  const providerFormula = String(
    checkoutPreview?.processing_fee_formula
    || checkoutPreview?.processing_fee_breakdown?.formula
    || (Number.isFinite(Number(checkoutPreview?.processing_fee_pct)) ? `${Number(checkoutPreview?.processing_fee_pct).toFixed(2)}%` : '')
    || tx('payment.feeTransparency.dynamicFormula', 'Calculated from live provider policy')
  );
  const hiddenSummaryRowKeys = useMemo(() => {
    const keys = Array.isArray(checkoutPreview?.fee_ui_visibility?.hidden_summary_row_keys)
      ? checkoutPreview.fee_ui_visibility.hidden_summary_row_keys
      : [];
    return new Set(keys.map((key: any) => String(key || '').trim().toLowerCase()).filter(Boolean));
  }, [checkoutPreview?.fee_ui_visibility?.hidden_summary_row_keys]);
  const hiddenProviderMetaKeys = useMemo(() => {
    const keys = Array.isArray(checkoutPreview?.fee_ui_visibility?.hidden_provider_meta_keys)
      ? checkoutPreview.fee_ui_visibility.hidden_provider_meta_keys
      : [];
    return new Set(
      [
        ...keys,
        'jurisdiction-source',
        'policy-source',
        'fee-policy-source',
        'source',
      ].map((key: any) => String(key || '').trim().toLowerCase()).filter(Boolean)
    );
  }, [checkoutPreview?.fee_ui_visibility?.hidden_provider_meta_keys]);
  const hideProviderFormula = Boolean(checkoutPreview?.fee_ui_visibility?.hide_provider_formula);
  const hidePolicyText = Boolean(checkoutPreview?.fee_ui_visibility?.hide_policy_text);
  const hideProviderCard = Boolean(checkoutPreview?.fee_ui_visibility?.hide_provider_card);

  const paymentSummaryRows = useMemo(() => {
    const rows: any[] = [
      {
        key: 'subtotal',
        label: tx('payment.feeTransparency.baseSubscription', 'Base Subscription Price'),
        value: `${checkoutPreview?.currency_symbol || '$'} ${formatPreviewAmount(checkoutPreview?.subtotal ?? effectivePlanPrice)}`,
        glossaryKey: 'subtotal' as const,
        icon: 'cash-outline',
        tone: colors.card,
      },
      {
        key: 'tax-fee',
        label: `${tx('payment.feeTransparency.applicableTax', 'Applicable Tax')} (${checkoutPreview?.jurisdiction?.country || browserLocaleSignals.region || '-'}${checkoutPreview?.jurisdiction?.state ? `-${checkoutPreview.jurisdiction.state}` : ''} @ ${checkoutPreview?.tax_rate_pct ?? 0}%)`,
        value: `${checkoutPreview?.currency_symbol || '$'} ${formatPreviewAmount(checkoutPreview?.tax_fee ?? 0)}`,
        glossaryKey: 'applicable_tax' as const,
        icon: 'receipt-outline',
        tone: colors.border,
      },
      {
        key: 'processing-fee',
        label: `${tx('payment.feeTransparency.processingFee', 'Payment Processing Fee')} (${selectedGatewayLabel})`,
        value: `${checkoutPreview?.currency_symbol || '$'} ${formatPreviewAmount(checkoutPreview?.processing_fee ?? 0)}`,
        glossaryKey: 'processing_fee' as const,
        icon: 'flash-outline',
        tone: colors.primarySoft,
      },
      {
        key: 'processing-formula',
        label: tx('payment.feeTransparency.providerFormula', 'Provider Fee Formula'),
        value: providerFormula,
        icon: 'construct-outline',
        tone: colors.card,
      },
    ];

    if (Array.isArray(checkoutPreview?.supported_cards) && checkoutPreview.supported_cards.length > 0) {
      rows.push({
        key: 'cards-supported',
        label: tx('payment.feeTransparency.cardsSupported', 'Cards Supported'),
        value: checkoutPreview.supported_cards.join(', ').toUpperCase(),
        icon: 'card-outline',
        tone: colors.card,
      });
    }

    return rows.filter((row) => !hiddenSummaryRowKeys.has(String(row.key).toLowerCase()));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    checkoutPreview,
    effectivePlanPrice,
    browserLocaleSignals.region,
    selectedGatewayLabel,
    providerFormula,
    hiddenSummaryRowKeys,
  ]);

  const providerMetaRows = useMemo(() => ([
    {
      key: 'tax-provider',
      label: tx('payment.feeTransparency.taxProvider', 'Tax Provider'),
      value: String(checkoutPreview?.tax_provider || '-'),
    },
  ].filter((row) => !hiddenProviderMetaKeys.has(String(row.key).toLowerCase()))), [checkoutPreview?.tax_provider, tx, hiddenProviderMetaKeys]);
  const providerFormulaDisplay = hideProviderFormula
    ? tx('payment.feeTransparency.providerFormulaHidden', 'Included in final total')
    : providerFormula;
  const providerPolicyText = hidePolicyText
    ? ''
    : `${tx('payment.feeTransparency.provider', 'Provider')}: ${checkoutPreview?.provider_display_name || selectedGatewayLabel} • ${tx('payment.feeTransparency.taxProvider', 'Tax Provider')}: ${checkoutPreview?.tax_provider || '-'}`;

  const telemetrySessionKey = useMemo(() => {
    const fallback = `subscription-session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    if (Platform.OS !== 'web' || typeof window === 'undefined') return fallback;
    try {
      const storageKey = 'subscription_conversion_session_key_v1';
      const existing = window.sessionStorage.getItem(storageKey);
      if (existing) return existing;
      window.sessionStorage.setItem(storageKey, fallback);
      return fallback;
    } catch (error) {
      handleAppRecoverableError({
        scope: 'subscription.payment.telemetry-session-key',
        error,
        message: 'Could not persist checkout telemetry session.',
        onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      return fallback;
    }
  }, []);

  const emitSubscribeSuccessTelemetry = useCallback(async (source: string) => {
    try {
      const width = Platform.OS === 'web' && typeof window !== 'undefined' ? window.innerWidth : 390;
      const deviceBucket = width < 768 ? 'mobile' : width < 1100 ? 'tablet' : 'desktop';
      await api.post('/subscription-conversion/telemetry', {
        session_key: telemetrySessionKey,
        event_type: 'subscribe_success',
        plan_id: planId,
        billing_period: billingPeriod,
        role: isAdmin ? 'admin' : 'regular_user',
        device_bucket: deviceBucket,
        route: '/subscription/payment',
        source,
      }, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [billingPeriod, isAdmin, planId, telemetrySessionKey]);

  const classifyCheckoutError = useCallback((error: any) => {
    const message = String(error?.message || '').toLowerCase();
    const detail = String(error?.response?.data?.detail || '').toLowerCase();
    const status = Number(error?.response?.status || error?.status || 0);
    if (status === 429 || detail.includes('rate')) return 'rate_limited';
    if (status >= 500) return 'server_error';
    if (status === 401 || status === 403) return 'auth_or_edge_blocked';
    if (message.includes('failed to fetch') || message.includes('network') || message.includes('abort') || detail.includes('aborted')) return 'network_or_edge_abort';
    if (detail.includes('cloudflare') || detail.includes('verify you are human')) return 'edge_challenge';
    return 'unknown';
  }, []);

  const postCheckoutInitWithRetry = useCallback(async (payload: any, paymentMethodForEvent: string) => {
    let lastError: any = null;
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      try {
        const response = await api.post('/subscriptions/initiate-checkout', payload);
        if (attempt > 1) {
          emitCheckoutFrontendEvent({
            event_type: 'checkout_init_recovered_after_retry',
            route: '/subscription/payment',
            plan_id: planId,
            billing_period: billingPeriod,
            payment_method: paymentMethodForEvent,
            currency: checkoutCurrency,
            reason: `recovered_on_attempt_${attempt}`,
          });
        }
        return response;
      } catch (error: any) {
        lastError = error;
        const errorClass = classifyCheckoutError(error);
        emitCheckoutFrontendEvent({
          event_type: 'checkout_init_failed',
          route: '/subscription/payment',
          plan_id: planId,
          billing_period: billingPeriod,
          payment_method: paymentMethodForEvent,
          currency: checkoutCurrency,
          reason: `${errorClass}::attempt_${attempt}`,
          error_message: String(error?.response?.data?.detail || error?.message || 'unknown').slice(0, 400),
        });
        if (attempt === 1 && (errorClass === 'network_or_edge_abort' || errorClass === 'edge_challenge' || errorClass === 'server_error')) {
          await new Promise((resolve) => setTimeout(resolve, 450));
          continue;
        }
      }
    }
    throw lastError;
  }, [billingPeriod, checkoutCurrency, classifyCheckoutError, emitCheckoutFrontendEvent, planId]);

  const handlePayPalPayment = async () => {
    setProcessing(true);
    setPaymentStep('processing');
    
    try {
      // Step 1: Create PayPal order on backend (auth token auto-attached by interceptor)
      const response = await postCheckoutInitWithRetry({
        plan_id: planId,
        billing_period: billingPeriod,
        payment_method: 'paypal',
        saved_card_id: selectedCardId || undefined,
        currency: checkoutPreview?.currency || checkoutCurrency,
        country_code: browserLocaleSignals.region || undefined,
        preferred_language: browserLocaleSignals.preferredLanguage || undefined,
        browser_language: browserLocaleSignals.browserLanguage || undefined,
        browser_languages: browserLocaleSignals.browserLanguages || undefined,
      }, 'paypal');

      const { order_id, checkout_url } = response.data;
      
      if (!checkout_url) {
        throw new Error('No checkout URL received from PayPal');
      }

      // Step 2: Open PayPal checkout
      if (Platform.OS === 'web') {
        try {
          const expiresAt = Date.now() + PAYMENT_PENDING_RESUME_TTL_MS;
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_URL_KEY, checkout_url);
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY, String(expiresAt));
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_METHOD_KEY, 'paypal');
        } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        window.location.href = checkout_url;
        return;
      }

      // On mobile, use WebBrowser
      const result = await WebBrowser.openBrowserAsync(checkout_url, {
        showInRecents: true,
        presentationStyle: WebBrowser.WebBrowserPresentationStyle.FULL_SCREEN,
      });

      // Step 3: After browser closes, try to capture the payment
      if (result.type === 'cancel') {
        setPaymentStep('form');
        setProcessing(false);
        const copy = getPaymentFailureCopy('cancelled', 'PayPal', tx);
        Alert.alert(copy.title, copy.message);
        return;
      }

      // Step 4: Attempt to capture the order
      try {
        const captureResponse = await api.post('/subscriptions/paypal/capture', {
          order_id: order_id,
          plan_id: planId,
          billing_period: billingPeriod,
        });

        if (captureResponse.data.success) {
          await refreshUser();
          await refreshAccessControl();
          await emitSubscribeSuccessTelemetry('payment_paypal_success');
          setPaymentStep('success');
        } else {
          throw new Error('Payment capture failed');
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'subscription.payment.paypal-status-verify',
          error,
          message: 'Could not verify PayPal payment status.',
          onRetry: () => { void handlePayPalPayment(); },
          notifyMode: 'dialog',
          userInitiated: true,
        });
        setPaymentStep('form');
        const copy = getPaymentFailureCopy('failed', 'PayPal', tx);
        Alert.alert(
          copy.title,
          copy.message,
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Try Again', onPress: () => handlePayPalPayment() }
          ]
        );
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'subscription.payment.paypal-payment',
        error,
        message: (error as any).response?.data?.detail || (error as any).message || 'Failed to process PayPal payment. Please try again.',
        onRetry: () => { void handlePayPalPayment(); },
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setPaymentStep('form');
      Alert.alert(
        'Payment Error',
        (error as any).response?.data?.detail || (error as any).message || 'Failed to process PayPal payment. Please try again.'
      );
    } finally {
      setProcessing(false);
    }
  };

  const handleCardPayment = async () => {
    setProcessing(true);
    setPaymentStep('processing');
    
    try {
      // Card payments use Stripe checkout
      const response = await postCheckoutInitWithRetry({
        plan_id: planId,
        billing_period: billingPeriod,
        payment_method: 'stripe',
        saved_card_id: selectedCardId || undefined,
        currency: checkoutCurrency,
        country_code: browserLocaleSignals.region || undefined,
        preferred_language: browserLocaleSignals.preferredLanguage || undefined,
        browser_language: browserLocaleSignals.browserLanguage || undefined,
        browser_languages: browserLocaleSignals.browserLanguages || undefined,
      }, 'stripe');

      const { checkout_url, session_id } = response.data;
      
      if (!checkout_url) {
        throw new Error('No checkout URL received from Stripe');
      }

      if (Platform.OS === 'web') {
        try {
          const expiresAt = Date.now() + PAYMENT_PENDING_RESUME_TTL_MS;
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_URL_KEY, checkout_url);
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_EXPIRY_KEY, String(expiresAt));
          window.localStorage.setItem(PAYMENT_PENDING_RESUME_METHOD_KEY, 'stripe');
        } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment.tsx#catch8', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        window.location.href = checkout_url;
        return;
      }

      // Mobile: Open Stripe checkout in browser
      const result = await WebBrowser.openBrowserAsync(checkout_url, {
        showInRecents: true,
        presentationStyle: WebBrowser.WebBrowserPresentationStyle.FULL_SCREEN,
      });

      if (result.type === 'cancel') {
        setPaymentStep('form');
        setProcessing(false);
        const copy = getPaymentFailureCopy('cancelled', 'Stripe', tx);
        Alert.alert(copy.title, copy.message);
        return;
      }

      // After browser closes, check Stripe payment status
      try {
        if (session_id) {
          const statusResp = await api.get(`/subscriptions/checkout-status/${session_id}`);
          if (statusResp.data.payment_status === 'paid') {
            await refreshUser();
            await refreshAccessControl();
            await emitSubscribeSuccessTelemetry('payment_stripe_success');
            setPaymentStep('success');
            return;
          }
        }
        setPaymentStep('form');
        const copy = getPaymentFailureCopy('failed', 'Stripe', tx);
        Alert.alert(
          copy.title,
          copy.message,
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Try Again', onPress: () => handleCardPayment() }
          ]
        );
      } catch (error) {
        handleAppRecoverableError({
          scope: 'subscription.payment.card-status-verify',
          error,
          message: 'Could not verify card payment status.',
          onRetry: () => { void handleCardPayment(); },
          notifyMode: 'dialog',
          userInitiated: true,
        });
        setPaymentStep('form');
        Alert.alert('Payment Status Unknown', 'Could not verify payment. Please check your subscription status.');
      }
    } catch (error) {
      handleAppRecoverableError({
        scope: 'subscription.payment.card-payment',
        error,
        message: (error as any).response?.data?.detail || (error as any).message || 'Failed to process payment. Please try again.',
        onRetry: () => { void handleCardPayment(); },
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setPaymentStep('form');
      Alert.alert(
        'Payment Error',
        (error as any).response?.data?.detail || (error as any).message || 'Failed to process payment. Please try again.'
      );
    } finally {
      setProcessing(false);
    }
  };

  const handlePayment = () => {
    const selectedAvailability = methodAvailability[paymentMethod === 'card' ? 'stripe' : paymentMethod];
    emitPricingGuardEvent({
      event_type: 'trust_checkout_conversion_click',
      plan_id: String(planId || ''),
      billing_period: billingPeriod,
      route: '/subscription/payment',
      payment_method: paymentMethod === 'card' ? 'stripe' : paymentMethod,
      currency: checkoutCurrency,
      canonical_price: Number.isFinite(canonicalPlanPrice) ? canonicalPlanPrice : null,
      reason: 'checkout_cta_click',
    });

    if (!selectedAvailability.available) {
      Alert.alert('Payment Method Unavailable', selectedAvailability.reason || 'This payment method is not currently configured.');
      return;
    }

    if (paymentMethod === 'fedapay') {
      const selectedSavedCardParam = selectedCardId
        ? `&savedCardId=${encodeURIComponent(String(selectedCardId))}`
        : '';
      const mmUrl = `/subscription/mobile-money?planId=${encodeURIComponent(String(planId || 'basic'))}&planName=${encodeURIComponent(String(planName || 'Plan'))}&planPrice=${encodeURIComponent(String(effectivePlanPrice))}&billingPeriod=${encodeURIComponent(String(billingPeriod || 'monthly'))}&provider=fedapay&currency=XOF${selectedSavedCardParam}`;
      router.push(mmUrl as any);
      return;
    }
    if (paymentMethod === 'apple_iap' || paymentMethod === 'google_iap') {
      router.push({
        pathname: '/subscription/mobile',
        params: {
          planId,
          planName,
          billingPeriod,
          provider: paymentMethod === 'apple_iap' ? 'apple' : 'google',
          origin: 'subscribe_pay',
          return_to: returnTo,
        },
      });
      return;
    }
    if (paymentMethod === 'paypal') {
      handlePayPalPayment();
    } else {
      handleCardPayment();
    }
  };

  // Success screen
  if (paymentStep === 'success') {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: isCompact ? 14 : 18, paddingBottom: 26, paddingTop: 22 }}>
          <View style={{ borderRadius: 18, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: isCompact ? 16 : 20 }} data-testid="payment-success-card" testID="payment-success-card">
            <SubscriptionSuccessPanel
              amountText={null}
              badgeText={null}
              ctaLabel={t('payment.success.startExploring', 'Start Exploring')}
              colors={{
                success: COLORS.success,
                successText: COLORS.successText,
                successSoft: COLORS.successSoft,
                text: COLORS.text,
                textMuted: COLORS.textSecondary,
                border: COLORS.border,
                bgSoft: COLORS.backgroundSecondary,
                primaryText: COLORS.primaryText,
              }}
              historyLabel={t('paymentResult.actions.viewHistory')}
              onPressCta={() => { stashSubscriptionReturnToast(returnTo, planName); router.replace(returnTo as any); }}
              onPressHistory={() => router.replace('/payment-history')}
              preCtaContent={(
                <SubscriptionUnlockedDestinationSummary
                  colors={{
                    success: COLORS.success,
                    successText: COLORS.successText,
                    text: COLORS.text,
                    textMuted: COLORS.textSecondary,
                    bgSoft: COLORS.backgroundSecondary,
                  }}
                  planName={planName}
                  providerKey={selectedGatewaySlug}
                  providerLabel={selectedGatewayLabel}
                  returnTarget={returnTo}
                  testIdPrefix="payment-web-unlocked"
                  tx={tx}
                />
              )}
              subtitle={t('payment.success.subtitle').replace('{plan}', planName)}
              title={t('payment.success.title', 'Payment Successful!')}
            />

            <EnterprisePaymentSummary
              prefix="payment-success-fee"
              title={tx('payment.feeTransparency.title', 'Checkout Fee Transparency')}
              colors={{
                text: COLORS.text,
                textSecondary: COLORS.textSecondary,
                textMuted: COLORS.textMuted,
                border: COLORS.border,
                surface: COLORS.surface,
                cardAlt: COLORS.backgroundSecondary,
              }}
              feeText={feeText}
              loading={false}
              error={''}
              rows={paymentSummaryRows}
              totalValue={`${checkoutPreview?.currency_symbol || '$'} ${formatPreviewAmount(checkoutPreview?.total_amount ?? effectivePlanPrice)}`}
              feeNote={checkoutPreview?.fee_visibility_note || tx('payment.feeTransparency.defaultNote', 'Tax Fee and Processing Fee are shown before payment.')}
              localization={checkoutPreview?.localization_context ? {
                jurisdiction: `${checkoutPreview?.jurisdiction?.country || '-'}${checkoutPreview?.jurisdiction?.state ? `-${checkoutPreview.jurisdiction.state}` : ''}`,
                languageLabel: `${(checkoutPreview?.localization_context?.resolved_language || 'en').toUpperCase()} • Confidence: ${Math.round(Number(checkoutPreview?.localization_context?.confidence || 0) * 100)}%`,
                fxLabel: `FX: 1 USD = ${formatPreviewAmount(checkoutPreview?.fx_rate || 1)} ${checkoutPreview?.currency || 'USD'} • Base price normalized from USD.`,
              } : null}
              policyText={providerPolicyText}
              providerKey={providerKeyForSummary}
              providerLabel={checkoutPreview?.provider_display_name || selectedGatewayLabel}
              providerFormula={providerFormulaDisplay}
              providerMetaRows={providerMetaRows}
              hideProviderCard={hideProviderCard}
            />

          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // Processing screen
  if (paymentStep === 'processing') {
    return (
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.processingContainer}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={styles.processingTitle}>{t('payment.processing.title', 'Processing Payment...')}</Text>
          <Text style={styles.processingSubtitle}>
            {paymentMethod === 'paypal'
              ? t('payment.processing.paypal', 'Complete your payment on PayPal. This window will update automatically.')
              : paymentMethod === 'fedapay'
                ? 'Preparing secure FedaPay redirect...'
                : paymentMethod === 'apple_iap'
                  ? 'Preparing App Store subscription handoff...'
                  : paymentMethod === 'google_iap'
                    ? 'Preparing Google Play subscription handoff...'
                : t('payment.processing.card', 'Securely processing your card payment...')}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()} data-testid="payment-back-button" testID="payment-back-button">
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t('payment.header.title', 'Payment')}</Text>
          <View style={styles.headerSpacer} />
        </View>

        <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
          {isVerySmallPhone && (
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, borderWidth: 1, borderColor: COLORS.border, borderRadius: 12, backgroundColor: COLORS.backgroundSecondary, paddingVertical: 8, paddingHorizontal: 10 }} data-testid="payment-compact-toggle-row" testID="payment-compact-toggle-row">
              <View style={{ flex: 1, paddingRight: 8 }}>
                <Text style={{ color: COLORS.text, fontSize: 12, fontWeight: '800' }} data-testid="payment-compact-toggle-title" testID="payment-compact-toggle-title">Compact payment mode</Text>
                <Text style={{ color: COLORS.textMuted, fontSize: 10, marginTop: 2 }} data-testid="payment-compact-toggle-subtitle" testID="payment-compact-toggle-subtitle">Optimizes checkout readability on small phones</Text>
              </View>
              <TouchableOpacity
                onPress={() => {
                  setCompactMode((prev) => !prev);
                  setCompactModeTouched(true);
                }}
                style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: compactMode ? COLORS.success : COLORS.border, backgroundColor: compactMode ? `${COLORS.success}22` : COLORS.surface }}
                data-testid="payment-compact-toggle-button"
                testID="payment-compact-toggle-button"
              >
                <Text style={{ color: compactMode ? COLORS.successText : COLORS.text, fontSize: 11, fontWeight: '800' }}>
                  {compactMode ? 'ON' : 'OFF'}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {priceGuardAutocorrected && !priceGuardError ? (
            <View style={{ borderWidth: 1, borderColor: COLORS.warningText, backgroundColor: COLORS.warningSoft, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 12 }} data-testid="payment-price-guard-autocorrected-banner" testID="payment-price-guard-autocorrected-banner">
              <Text style={{ color: COLORS.warningText, fontSize: 11, fontWeight: '700' }}>
                Live platform pricing replaced an outdated route price automatically.
              </Text>
            </View>
          ) : null}

          {priceGuardWarning ? (
            <View style={{ borderWidth: 1, borderColor: COLORS.warningText, backgroundColor: COLORS.warningSoft, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 12 }} data-testid="payment-price-guard-warning-banner" testID="payment-price-guard-warning-banner">
              <Text style={{ color: COLORS.warningText, fontSize: 11, fontWeight: '700' }}>{priceGuardWarning}</Text>
            </View>
          ) : null}

          {priceGuardError ? (
            <View style={{ borderWidth: 1, borderColor: COLORS.error, backgroundColor: COLORS.errorSoft, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 12 }} data-testid="payment-price-guard-error-banner" testID="payment-price-guard-error-banner">
              <Text style={{ color: COLORS.errorText, fontSize: 11, fontWeight: '700' }}>{priceGuardError}</Text>
            </View>
          ) : null}

          {/* Resume Pending Checkout CTA */}
          {pendingResumeUrl ? (
            <View
              style={{ marginBottom: 16, borderRadius: 12, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: `${COLORS.primary}12`, padding: 12 }}
              data-testid="payment-resume-pending-cta-card"
              testID="payment-resume-pending-cta-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <Ionicons name="refresh-circle-outline" size={16} color={COLORS.primary} />
                <Text style={{ color: COLORS.text, fontSize: 12, fontWeight: '800' }} data-testid="payment-resume-pending-title" testID="payment-resume-pending-title">
                  Resume pending {pendingResumeMethod === 'paypal' ? 'PayPal' : 'Stripe'} checkout
                </Text>
              </View>
              {resumeCountdownLabel ? (
                <Text style={{ color: COLORS.warningText, fontSize: 11, marginBottom: 4, fontWeight: '700' }} data-testid="payment-resume-countdown" testID="payment-resume-countdown">
                  Link expires soon: {resumeCountdownLabel}
                </Text>
              ) : null}
              {pendingResumeMeta ? (
                <Text style={{ color: COLORS.textSecondary, fontSize: 10, marginBottom: 8 }} data-testid="payment-resume-pending-meta" testID="payment-resume-pending-meta">
                  {pendingResumeMeta}
                </Text>
              ) : null}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <TouchableOpacity
                  onPress={resumePendingCheckout}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary, paddingHorizontal: 14, paddingVertical: 7 }}
                  data-testid="payment-resume-button"
                  testID="payment-resume-button"
                >
                  <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>Resume</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={clearPendingResume}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.backgroundSecondary, paddingHorizontal: 14, paddingVertical: 7 }}
                  data-testid="payment-dismiss-resume-button"
                  testID="payment-dismiss-resume-button"
                >
                  <Text style={{ color: COLORS.textSecondary, fontSize: 11, fontWeight: '700' }}>Dismiss</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : null}

          {/* Order Summary */}
          <View style={styles.summaryCard}>
            <Text style={styles.summaryTitle}>{t('payment.orderSummary.title', 'Order Summary')}</Text>
            <View style={styles.summaryRow}>
              <View style={styles.summaryPlan}>
                <View style={styles.planIconBox}>
                  <Ionicons name="diamond" size={20} color={COLORS.premium} />
                </View>
                <View>
                  <Text style={styles.planNameText}>{t('payment.orderSummary.planName').replace('{plan}', planName)}</Text>
                  <Text style={styles.planPeriodText}>{t('payment.orderSummary.billed').replace('{period}', billingPeriod)}</Text>
                </View>
              </View>
              <Text style={styles.planPriceText}>${formatPreviewAmount(effectivePlanPrice)}</Text>
            </View>
            <View style={styles.summaryDivider} />
            <View style={styles.totalRow}>
              <Text style={styles.totalLabel}>{t('payment.orderSummary.total', 'Total')}</Text>
              <Text style={styles.totalPrice}>${formatPreviewAmount(effectivePlanPrice)}/{billingPeriod === 'monthly' ? 'mo' : 'yr'}</Text>
            </View>
          </View>

          {/* Payment Method Selection */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>{t('payment.method.title', 'Payment Method')}</Text>
            <PaymentMethodSelector
              mode="select"
              options={visiblePaymentMethodOptions}
              availability={methodAvailability}
              selected={paymentMethod === 'card' ? 'stripe' : paymentMethod}
              onSelect={(id) => setPaymentMethod(id === 'stripe' ? 'card' : id)}
              colors={{
                surface: COLORS.surface,
                border: COLORS.border,
                text: COLORS.text,
                textMuted: COLORS.textMuted,
                primary: COLORS.primary,
                warningText: COLORS.warningText,
                successText: COLORS.successText,
              }}
              containerTestId="subscription-payment-method-selector"
            />

            {isAdmin && (
              <>
                <View
                  style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: selectedHealthTone.border, backgroundColor: selectedHealthTone.bg, padding: 10 }}
                  data-testid={`subscription-payment-${selectedGatewaySlug}-health-badge`} testID={`subscription-payment-${selectedGatewaySlug}-health-badge`}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={selectedHealthTone.icon as any} size={14} color={selectedHealthTone.color} />
                    <Text
                      style={{ color: selectedHealthTone.color, fontSize: 11, fontWeight: '800' }}
                      data-testid={`subscription-payment-${selectedGatewaySlug}-health-status`} testID={`subscription-payment-${selectedGatewaySlug}-health-status`}
                    >
                      {selectedGatewayLabel} {t('payment.gateway.statusLabel', 'Status')}: {selectedGatewayHealth.status === 'healthy' ? t('payment.gateway.ready', 'Ready') : selectedGatewayHealth.status === 'unavailable' ? t('payment.gateway.unavailable', 'Unavailable') : selectedGatewayHealth.status === 'degraded' ? t('payment.gateway.degraded', 'Degraded') : t('payment.gateway.loading', 'Loading')}
                    </Text>
                  </View>
                  <Text style={{ color: COLORS.textSecondary, fontSize: 10, marginTop: 4 }} data-testid={`subscription-payment-${selectedGatewaySlug}-health-message`} testID={`subscription-payment-${selectedGatewaySlug}-health-message`}>
                    {selectedGatewayHealth.message} {selectedGatewayHealth.mode ? `Mode: ${selectedGatewayHealth.mode}.` : ''}
                  </Text>
                  <HeartbeatPulse
                    tick={paymentStatusHeartbeatSec}
                    style={{ marginTop: 4 }}
                    warningAfterSeconds={60}
                    criticalAfterSeconds={120}
                    dataTestId={`subscription-payment-${selectedGatewaySlug}-health-heartbeat`}
                    testID={`subscription-payment-${selectedGatewaySlug}-health-heartbeat`}
                  >
                    <Text style={{ color: COLORS.textSecondary, fontSize: 10, fontWeight: '600' }}>
                      {paymentStatusHeartbeatSec >= 120 ? t('payment.gateway.criticalStale', 'Critical stale') : paymentStatusHeartbeatSec >= 60 ? t('payment.gateway.stale', 'Stale') : t('payment.gateway.lastChecked', 'Last checked')} {paymentStatusHeartbeatSec}s {t('payment.gateway.ago', 'ago')}
                    </Text>
                  </HeartbeatPulse>
                </View>

                {emailServiceAvailable === false ? (
                  <View
                    style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.warningSoft, backgroundColor: colors.warningSoft, padding: 10 }}
                    data-testid="subscription-payment-email-service-warning" testID="subscription-payment-email-service-warning"
                  >
                    <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '800' }} data-testid="subscription-payment-email-service-warning-title" testID="subscription-payment-email-service-warning-title">
                      Email receipt service is currently unavailable
                    </Text>
                    <Text style={{ color: COLORS.textSecondary, fontSize: 10, marginTop: 4 }} data-testid="subscription-payment-email-service-warning-message" testID="subscription-payment-email-service-warning-message">
                      Your payment still works. In-app confirmations and admin in-app alerts remain active while email delivery is unavailable.
                    </Text>
                  </View>
                ) : null}
              </>
            )}

            <EnterprisePaymentSummary
              prefix="subscription-payment-fee"
              title={tx('payment.feeTransparency.title', 'Checkout Fee Transparency')}
              colors={{
                text: COLORS.text,
                textSecondary: COLORS.textSecondary,
                textMuted: COLORS.textMuted,
                border: COLORS.border,
                surface: COLORS.surface,
                cardAlt: COLORS.backgroundSecondary,
              }}
              feeText={feeText}
              loading={checkoutPreviewLoading}
              error={checkoutPreviewError ? tx('payment.feeTransparency.previewUnavailable', 'Live preview unavailable. Showing estimated summary.') : ''}
              rows={paymentSummaryRows}
              totalValue={`${checkoutPreview?.currency_symbol || '$'} ${formatPreviewAmount(checkoutPreview?.total_amount ?? effectivePlanPrice)}`}
              feeNote={checkoutPreview?.fee_visibility_note || tx('payment.feeTransparency.defaultNote', 'Tax Fee and Processing Fee are shown before payment.')}
              localization={checkoutPreview?.localization_context ? {
                jurisdiction: `${checkoutPreview?.jurisdiction?.country || '-'}${checkoutPreview?.jurisdiction?.state ? `-${checkoutPreview.jurisdiction.state}` : ''}`,
                languageLabel: `${(checkoutPreview?.localization_context?.resolved_language || 'en').toUpperCase()} • Confidence: ${Math.round(Number(checkoutPreview?.localization_context?.confidence || 0) * 100)}%`,
                fxLabel: `FX: 1 USD = ${formatPreviewAmount(checkoutPreview?.fx_rate || 1)} ${checkoutPreview?.currency || 'USD'} • Base price normalized from USD.`,
              } : null}
              policyText={providerPolicyText}
              providerKey={providerKeyForSummary}
              providerLabel={checkoutPreview?.provider_display_name || selectedGatewayLabel}
              providerFormula={providerFormulaDisplay}
              providerMetaRows={providerMetaRows}
              hideProviderCard={hideProviderCard}
            />
          </View>

          <View style={styles.section}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <Text style={styles.sectionTitle} data-testid="subscription-saved-card-title" testID="subscription-saved-card-title">Saved Card for Checkout</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <TouchableOpacity onPress={() => router.push('/settings/payment-cards')} data-testid="subscription-manage-cards-button" testID="subscription-manage-cards-button">
                  <Text style={{ color: COLORS.primary, fontSize: 12, fontWeight: '700' }}>Manage</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => router.push('/settings/payment-cards')} data-testid="subscription-add-cards-button" testID="subscription-add-cards-button">
                  <Text style={{ color: COLORS.primary, fontSize: 12, fontWeight: '800' }}>Add Card</Text>
                </TouchableOpacity>
              </View>
            </View>

            <Text style={{ color: COLORS.textMuted, fontSize: 10, marginBottom: 8 }} data-testid="subscription-saved-card-compatibility-note" testID="subscription-saved-card-compatibility-note">
              Checkout-ready card context is available across Stripe, PayPal, FedaPay, Apple IAP, and Google IAP.
            </Text>

            {savedCards.length === 0 ? (
              <View style={{ borderRadius: 12, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.surface, padding: 12 }} data-testid="subscription-no-saved-cards-warning" testID="subscription-no-saved-cards-warning">
                <Text style={{ color: COLORS.textSecondary, fontSize: 12 }}>
                  Add a valid non-expired card to use saved-card checkout context across Stripe, PayPal, FedaPay, and IAP records.
                </Text>
              </View>
            ) : (
              <View style={{ gap: 8 }} data-testid="subscription-saved-cards-selector" testID="subscription-saved-cards-selector">
                {savedCards.map((card) => {
                  const active = selectedCardId === card.card_id;
                  return (
                    <TouchableOpacity
                      key={card.card_id}
                      onPress={() => setSelectedCardId(card.card_id)}
                      style={{
                        borderWidth: 1.5,
                        borderColor: active ? COLORS.primary : COLORS.border,
                        borderRadius: 12,
                        backgroundColor: active ? `${COLORS.primary}10` : COLORS.surface,
                        padding: 12,
                        flexDirection: 'row',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                      data-testid={`subscription-saved-card-option-${card.card_id}`} testID={`subscription-saved-card-option-${card.card_id}`}
                    >
                      <View>
                        <Text style={{ color: COLORS.text, fontSize: 13, fontWeight: '700' }}>
                          {String(card.card_type || 'card').toUpperCase()} •••• {card.last_four}
                        </Text>
                        <Text style={{ color: COLORS.textSecondary, fontSize: 11, marginTop: 2 }}>
                          Expires {String(card.expiry_month).padStart(2, '0')}/{String(card.expiry_year).slice(-2)} {card.is_default ? '• Default' : ''}
                        </Text>
                      </View>
                      <Ionicons name={active ? 'checkmark-circle' : 'ellipse-outline'} size={20} color={active ? COLORS.primary : COLORS.textMuted} />
                    </TouchableOpacity>
                  );
                })}
              </View>
            )}

            {selectedSavedCard ? (
              <Text style={{ color: COLORS.textMuted, fontSize: 10, marginTop: 8 }} data-testid="subscription-selected-card-context-note" testID="subscription-selected-card-context-note">
                Selected: {String(selectedSavedCard.card_type).toUpperCase()} •••• {selectedSavedCard.last_four}
              </Text>
            ) : null}
          </View>

          {/* Card Details - Stripe handles the card form */}
          {paymentMethod === 'card' && (
            <View style={styles.section}>
              <View style={styles.paypalInfo}>
                <View style={[styles.paypalIconContainer, { backgroundColor: (globalThis as any).__alphaColor(COLORS.primary, '10') }]}>
                  <Ionicons name="card" size={44} color={COLORS.primary} />
                </View>
                <Text style={styles.paypalTitle}>{t('payment.cardSection.title', 'Pay with Stripe')}</Text>
                <Text style={styles.paypalText}>
                  {t('payment.cardSection.subtitle', "You'll be securely redirected to Stripe to enter your card details and complete your payment.")}
                </Text>
              </View>
            </View>
          )}

          {/* PayPal Section */}
          {paymentMethod === 'paypal' && (
            <View style={styles.section}>
              <View style={styles.paypalInfo}>
                <View style={styles.paypalIconContainer}>
                  <Ionicons name="logo-paypal" size={44} color={COLORS.paypal} />
                </View>
                <Text style={styles.paypalTitle}>{t('payment.paypalSection.title', 'Pay with PayPal')}</Text>
                <Text style={styles.paypalText}>
                  {t('payment.paypalSection.subtitle', "You'll be securely redirected to PayPal to complete your payment. Log in with your PayPal account or pay with a debit/credit card.")}
                </Text>
              </View>
            </View>
          )}

          {/* FedaPay Section */}
          {paymentMethod === 'fedapay' && (
            <View style={styles.section}>
              <View style={styles.paypalInfo}>
                <View style={[styles.paypalIconContainer, { backgroundColor: `${COLORS.success}15` }]}> 
                  <Ionicons name="cash-outline" size={44} color={COLORS.successText} />
                </View>
                <Text style={styles.paypalTitle}>Pay with FedaPay</Text>
                <Text style={styles.paypalText}>
                  Continue to secure FedaPay checkout to complete your FedaPay payment.
                </Text>
              </View>
            </View>
          )}

          {paymentMethod === 'apple_iap' && (
            <View style={styles.section}>
              <View style={styles.paypalInfo}>
                <View style={[styles.paypalIconContainer, { backgroundColor: `${COLORS.primary}15` }]}> 
                  <Ionicons name="logo-apple" size={44} color={COLORS.primary} />
                </View>
                <Text style={styles.paypalTitle}>Continue with Apple IAP</Text>
                <Text style={styles.paypalText}>
                  You will be redirected to the mobile subscription flow to complete App Store checkout.
                </Text>
              </View>
            </View>
          )}

          {paymentMethod === 'google_iap' && (
            <View style={styles.section}>
              <View style={styles.paypalInfo}>
                <View style={[styles.paypalIconContainer, { backgroundColor: `${COLORS.primary}15` }]}> 
                  <Ionicons name="logo-google-playstore" size={44} color={COLORS.primary} />
                </View>
                <Text style={styles.paypalTitle}>Continue with Google IAP</Text>
                <Text style={styles.paypalText}>
                  You will be redirected to the mobile subscription flow to complete Google Play checkout.
                </Text>
              </View>
            </View>
          )}

          <SecurePaymentAssurancePanel
            provider={(paymentMethod === 'card' ? 'stripe' : paymentMethod === 'apple_iap' || paymentMethod === 'google_iap' ? 'stripe' : paymentMethod) as 'stripe' | 'paypal' | 'fedapay'}
            context="checkout"
            panelTestId="subscription-payment-secure-assurance-panel"
          />

          {/* Pay Button */}
          {Platform.OS === 'web' ? <div data-testid="payment-submit-button" /> : null}
          <TouchableOpacity
            style={[
              styles.payButton, 
              submitDisabled && styles.payButtonDisabled,
              paymentMethod === 'paypal' && styles.paypalButton
            ]}
            onPress={handlePayment}
            disabled={submitDisabled}
            data-testid="payment-submit-button" testID="payment-submit-button"
          >
            {processing ? (
              <ActivityIndicator color={colors.primaryText} />
            ) : (
              <>
                <Ionicons 
                  name={paymentMethod === 'paypal' ? 'logo-paypal' : paymentMethod === 'fedapay' ? 'cash-outline' : paymentMethod === 'apple_iap' ? 'logo-apple' : paymentMethod === 'google_iap' ? 'logo-google-playstore' : 'lock-closed'} 
                  size={20} 
                  color={colors.primaryText} 
                />
                <Text style={styles.payButtonText}>
                  {paymentMethod === 'paypal'
                    ? `Pay with PayPal - ${checkoutPreview?.currency_symbol || '$'}${formatPreviewAmount(checkoutPreview?.total_amount || effectivePlanPrice)}` 
                    : paymentMethod === 'fedapay'
                      ? `Continue with FedaPay - ${checkoutPreview?.currency_symbol || '$'}${formatPreviewAmount(checkoutPreview?.total_amount || effectivePlanPrice)}`
                      : paymentMethod === 'apple_iap'
                        ? `Continue with Apple IAP - ${checkoutPreview?.currency_symbol || '$'}${formatPreviewAmount(checkoutPreview?.total_amount || effectivePlanPrice)}`
                        : paymentMethod === 'google_iap'
                          ? `Continue with Google IAP - ${checkoutPreview?.currency_symbol || '$'}${formatPreviewAmount(checkoutPreview?.total_amount || effectivePlanPrice)}`
                      : `Pay with Stripe - ${checkoutPreview?.currency_symbol || '$'}${formatPreviewAmount(checkoutPreview?.total_amount || effectivePlanPrice)}`
                  }
                </Text>
              </>
            )}
          </TouchableOpacity>

          {!!submitDisableReason && submitDisabled ? (
            <Text
              style={{ color: COLORS.textMuted, fontSize: 11, textAlign: 'center', marginTop: 8 }}
              data-testid="payment-submit-disabled-reason"
              testID="payment-submit-disabled-reason"
            >
              {submitDisableReason}
            </Text>
          ) : null}

          {/* Terms */}
          <Text style={styles.termsText}>
            {t('payment.terms', 'By subscribing, you agree to our Terms of Service and Privacy Policy. Your subscription will auto-renew. Cancel anytime from your subscription settings.')}
          </Text>

          <View style={styles.spacer} />
        </ScrollView>
    </SafeAreaView>
  );
}
