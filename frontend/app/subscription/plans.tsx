import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, useWindowDimensions, Platform, Modal, TextInput, ImageBackground,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useGlobalSearchParams, useLocalSearchParams, useRouter } from 'expo-router';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import { fetchSubscriptionGatewayConfig, resolvePaymentMethodsFromGatewayConfig } from '../../src/services/subscriptionPaymentMethods';
import { PaymentMethodSelector } from '../../src/components/payment/PaymentMethodSelector';
import { EnterprisePaymentSummary } from '../../src/components/payment/EnterprisePaymentSummary';
import { SecurePaymentAssurancePanel } from '../../src/components/payment/SecurePaymentAssurancePanel';
import { useTheme } from '../../src/context/ThemeContext';
import AppShell from '../../src/components/AppShell';
import SubscriptionBadge from '../../src/components/SubscriptionBadge';
import { useAutoRefresh } from '../../src/hooks/useAutoRefresh';
import { GallerySkeleton } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';
import { useViewportWidth } from '../../src/hooks/useViewportWidth';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { getUpgradeCopyForPath } from '../../src/utils/routeUpgradeCopy';
import { buildFrontendPricingSaveLabel } from '../../src/config/pricingPolicy';
import { normalizeReturnTarget } from '../../src/utils/subscriptionReturnTarget';
import { notificationEvents } from '../../src/utils/notificationEvents';
import { getPaymentFailureCopy, normalizePaymentFailureState } from '../../src/utils/paymentFailureCopy';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';
import { buildAnalyticsSource } from '../../src/utils/buildAnalyticsSource';
import { withAlpha } from '../../src/utils/colorAlpha';

const PLAN_ICONS = { free: 'person', basic: 'star', premium: 'diamond' };

const ZERO_DECIMAL = new Set(['JPY', 'KRW', 'XOF', 'XAF']);
const POPULAR_CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'INR', 'BRL', 'NGN', 'XOF', 'ZAR'];

function detectCurrencyFromLocale(): string {
  if (typeof navigator === 'undefined') return 'USD';
  try {
    const lang = navigator.language || 'en-US';
    const regionMap: Record<string, string> = {
      'FR': 'EUR', 'DE': 'EUR', 'IT': 'EUR', 'ES': 'EUR', 'NL': 'EUR', 'BE': 'EUR', 'GB': 'GBP',
      'CA': 'CAD', 'AU': 'AUD', 'JP': 'JPY', 'IN': 'INR', 'BR': 'BRL', 'KR': 'KRW', 'MX': 'MXN',
      'NG': 'NGN', 'ZA': 'ZAR', 'AE': 'AED', 'SA': 'SAR', 'TR': 'TRY', 'TH': 'THB', 'PL': 'PLN', 'SE': 'SEK',
      'SN': 'XOF', 'CI': 'XOF', 'BF': 'XOF', 'ML': 'XOF', 'CM': 'XAF', 'GH': 'GHS',
    };
    const parts = lang.split('-');
    return regionMap[parts[1]?.toUpperCase() || ''] || 'USD';
  } catch { return 'USD'; }
}

function getMinutesSinceIso(value?: string | null, nowMs = Date.now()): number | null {
  if (!value) return null;
  const parsedMs = Date.parse(value);
  if (!Number.isFinite(parsedMs)) return null;
  const diffMs = Math.max(0, nowMs - parsedMs);
  return Math.floor(diffMs / 60000);
}

type CurrencyInfo = { code: string; symbol: string; name: string; rate: number; stripe_supported: boolean };

export default function SubscriptionScreen() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const globalParams = useGlobalSearchParams();
  const { width: rnWidth } = useWindowDimensions();
  const viewportWidth = useViewportWidth();
  const sw = Platform.OS === 'web' ? viewportWidth : rnWidth;
  const { user, refreshUser, isAuthenticated } = useAuth();
  useEffect(() => {
    if (isAuthenticated) return;
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      router.replace('/welcome?section=pricing' as any);
      return;
    }

    const currentPath = String(window.location.pathname || '').replace(/\/+$/, '') || '/';
    if (currentPath === '/subscription/plans') {
      router.replace('/welcome?section=pricing' as any);
    }
  }, [isAuthenticated, router]);

  const hasAdminFlag = hasAdminConsoleVisibility(user as any);
  const { colors, darkMode, languageCode, themeMode, setThemeMode } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const localizePlanLabel = useCallback((planId: string, field: 'name' | 'description', fallback: string) => {
    return tx(`subscriptionPlans.plan.${String(planId || '').trim().toLowerCase()}.${field}`, fallback);
  }, [tx]);
  const localizePlanArray = useCallback((planId: string, type: 'features' | 'limitations', values: any[] = []) => {
    return values.map((value, index) => tx(`subscriptionPlans.plan.${String(planId || '').trim().toLowerCase()}.${type}.${index}`, String(value || '')));
  }, [tx]);
  const yearlySaveBadgeText = useMemo(() => buildFrontendPricingSaveLabel(t('pricing.saveDynamic'), 'SAVE {pct}%'), [t]);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [billingPeriod, setBillingPeriod] = useState('monthly');
  const [cancelling, setCancelling] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<any>(null);
  const [showPaymentPicker, setShowPaymentPicker] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [cancelStep, setCancelStep] = useState<'reason' | 'confirm' | 'done'>('reason');
  const [cancelReason, setCancelReason] = useState('');
  const [cancelResult, setCancelResult] = useState<any>(null);
  const [currencies, setCurrencies] = useState<CurrencyInfo[]>([]);
  const [selectedCurrency, setSelectedCurrency] = useState('USD');
  const [currencySymbol, setCurrencySymbol] = useState('$');
  const [showCurrencyPicker, setShowCurrencyPicker] = useState(false);
  const [fedapayPolicyUpdatedAt, setFedapayPolicyUpdatedAt] = useState<string>('');
  const [fedapaySyncClockMs, setFedapaySyncClockMs] = useState(Date.now());
  const [gatewayConfig, setGatewayConfig] = useState<any>(null);
  const [conversionSummary, setConversionSummary] = useState<any>(null);
  const [conversionSummaryLoading, setConversionSummaryLoading] = useState(false);
  const [dismissedBannerKey, setDismissedBannerKey] = useState('');
  const [autoHiddenBannerKey, setAutoHiddenBannerKey] = useState('');
  const [showPaymentDetailsModal, setShowPaymentDetailsModal] = useState(false);
  const [paymentDetailsLoading, setPaymentDetailsLoading] = useState(false);
  const [paymentDetails, setPaymentDetails] = useState<{ payments: any[]; transactions: any[] }>({ payments: [], transactions: [] });
  const [copiedTransactionId, setCopiedTransactionId] = useState('');
  const [detailGatewayFilter, setDetailGatewayFilter] = useState<'all' | 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap'>('all');
  const [detailDateFromInput, setDetailDateFromInput] = useState('');
  const [detailDateToInput, setDetailDateToInput] = useState('');
  const [appliedDetailDateFrom, setAppliedDetailDateFrom] = useState('');
  const [appliedDetailDateTo, setAppliedDetailDateTo] = useState('');
  const [downloadingReceiptId, setDownloadingReceiptId] = useState('');
  const [downloadingInvoiceId, setDownloadingInvoiceId] = useState('');
  const [bulkExportingDocType, setBulkExportingDocType] = useState<'' | 'receipt' | 'invoice'>('');
  const [modalToast, setModalToast] = useState<{ type: 'success' | 'error' | 'info'; message: string } | null>(null);
  const [selectedPaymentDetailIndex, setSelectedPaymentDetailIndex] = useState(0);
  const [plansContentWidth, setPlansContentWidth] = useState(0);
  const trackedPlanViewsRef = useRef<Set<string>>(new Set());
  const trackedSuccessRef = useRef(false);

  const upgradeFromPath = useMemo(() => {
    const local = String(params?.upgrade_from || '').trim();
    const global = String((globalParams as any)?.upgrade_from || '').trim();
    return decodeURIComponent(local || global || '');
  }, [params, globalParams]);

  const upgradeReason = useMemo(() => {
    const local = String(params?.upgrade_reason || '').trim();
    const global = String((globalParams as any)?.upgrade_reason || '').trim();
    return decodeURIComponent(local || global || '');
  }, [params, globalParams]);

  const upgradeContext = useMemo(() => {
    const local = String(params?.upgrade_context || '').trim();
    const global = String((globalParams as any)?.upgrade_context || '').trim();
    return decodeURIComponent(local || global || '');
  }, [params, globalParams]);

  const upgradeTitleOverride = useMemo(() => {
    const local = String(params?.upgrade_title || '').trim();
    const global = String((globalParams as any)?.upgrade_title || '').trim();
    return decodeURIComponent(local || global || '');
  }, [params, globalParams]);

  const recommendedPlan = useMemo(() => {
    const local = String(params?.recommended_plan || '').trim().toLowerCase();
    const global = String((globalParams as any)?.recommended_plan || '').trim().toLowerCase();
    const value = local || global;
    return value === 'premium' ? 'premium' : 'basic';
  }, [params, globalParams]);

  const contextualUpgradeCopy = useMemo(() => {
    if (!upgradeFromPath) return null;
    return getUpgradeCopyForPath(upgradeFromPath);
  }, [upgradeFromPath]);

  const contextualUpgradeTitle = useMemo(() => {
    return upgradeTitleOverride || contextualUpgradeCopy?.title || '';
  }, [contextualUpgradeCopy?.title, upgradeTitleOverride]);

  const contextualUpgradeMeta = useMemo(() => {
    const segments = [
      `${tx('subscriptionPlans.context.recommendedPlan', 'Recommended plan')}: ${tx(`subscriptionPlans.plan.${recommendedPlan}.name`, recommendedPlan.toUpperCase())}`,
      `${tx('subscriptionPlans.context.reason', 'Reason')}: ${upgradeReason || tx('subscriptionPlans.context.routePolicy', 'route policy')}`,
    ];
    if (upgradeContext) {
      segments.push(`${tx('subscriptionPlans.context.tryingToOpen', 'Trying to open')}: ${upgradeContext}`);
    }
    return segments.join(' · ');
  }, [recommendedPlan, tx, upgradeReason, upgradeContext]);

  const contextualUpgradeEyebrow = useMemo(() => {
    if (!upgradeContext) return tx('subscriptionPlans.context.planMatch', 'PLAN MATCH');
    return `${tx('subscriptionPlans.context.planMatch', 'PLAN MATCH')} · ${upgradeContext.toUpperCase()}`;
  }, [tx, upgradeContext]);

  const resolvedUpgradeReturnTarget = useMemo(() => normalizeReturnTarget(upgradeFromPath || '/dashboard'), [upgradeFromPath]);

  const pageHorizontalPadding = sw >= 1280 ? 28 : sw >= 760 ? 22 : 16;
  const responsiveWidth = plansContentWidth > 0 ? plansContentWidth : Math.max(320, sw - (pageHorizontalPadding * 2));
  const isWide = responsiveWidth >= 760;
  const isPhone = responsiveWidth < 640;
  const stackHeroControls = responsiveWidth < 1040;
  const planColumnCount = responsiveWidth >= 1320 ? 3 : responsiveWidth >= 760 ? 2 : 1;
  const planGridGap = responsiveWidth >= 1180 ? 18 : 14;
  const planCardWidth = planColumnCount > 1
    ? Math.max(280, (responsiveWidth - (planGridGap * (planColumnCount - 1))) / planColumnCount)
    : responsiveWidth;

  const C = useMemo(() => ({
    ...colors,
    success: colors.success, warning: colors.warning, error: colors.error,
    primary: colors.primary, bg: colors.bg, bgSoft: colors.bgSoft,
    card: colors.card, text: colors.text, textSec: colors.textSec,
    textMuted: colors.textMuted, border: colors.border,
    cardAlt: (colors as any).cardAlt || colors.bgSoft,
    surface: (colors as any).surface || colors.card,
    surfaceElevated: (colors as any).surfaceElevated || colors.card,
    borderStrong: (colors as any).borderStrong || colors.border,
  }), [colors]);

  const heroOverlayColor = useMemo(
    () => withAlpha(C.surfaceElevated, darkMode ? 'D8' : 'E6'),
    [C.surfaceElevated, darkMode],
  );
  const heroControlSurface = useMemo(
    () => withAlpha(C.surface, darkMode ? 'C8' : 'F0'),
    [C.surface, darkMode],
  );
  const premiumBadgeSurface = useMemo(
    () => withAlpha(colors.warningText, darkMode ? '20' : '14'),
    [colors.warningText, darkMode],
  );
  const premiumBadgeBorder = useMemo(
    () => withAlpha(colors.warningText, darkMode ? '55' : '38'),
    [colors.warningText, darkMode],
  );

  const headingFont = Platform.OS === 'web' ? { fontFamily: 'Outfit, sans-serif' as any } : null;
  const bodyFont = Platform.OS === 'web' ? { fontFamily: 'IBM Plex Sans, sans-serif' as any } : null;
  const heroImageUri = darkMode
    ? 'https://static.prod-images.emergentagent.com/jobs/dea1945e-3c72-4184-a9a0-e1c8a2ab8bbe/images/b5d6e6b5d83742f12c642354fdb62dc44cf6638d7f1f41a10f23318604f12af5.png'
    : 'https://static.prod-images.emergentagent.com/jobs/dea1945e-3c72-4184-a9a0-e1c8a2ab8bbe/images/4a6fd40b332bdfb7fd82e92652a3bc3c1053f8932f3a83851d62f487d94ebe1b.png';

  useEffect(() => {
    // Load user's saved currency preference, fall back to locale detection
    const detected = detectCurrencyFromLocale();
    const saved = user?.currency_preference;
    const initial = saved || detected;
    setSelectedCurrency(initial);
    api.get('/payments/currencies', { silentLoading: true })
      .then(({ data }) => {
        setCurrencies(data.currencies || []);
        const valid = (data.currencies || []).find((c: CurrencyInfo) => c.code === initial);
        if (valid) { setCurrencySymbol(valid.symbol); } else { setSelectedCurrency('USD'); }
        if (!saved && (!valid || initial === 'USD')) {
          // Geo fallback: generic locales carry no region — resolve currency via IP.
          api.get('/geo/detect', { silentLoading: true })
            .then(({ data: geo }) => {
              const geoCurrency = String(geo?.default_currency || '').toUpperCase();
              const geoValid = (data.currencies || []).find((c: CurrencyInfo) => c.code === geoCurrency);
              if (geoCurrency !== 'USD' && geoValid) {
                setSelectedCurrency(geoCurrency);
                setCurrencySymbol(geoValid.symbol);
              }
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
  }, [user?.currency_preference]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadPlans(); }, [languageCode, selectedCurrency]);
  useAutoRefresh(loadPlans, { intervalMs: 30000 });

  useEffect(() => {
    let mounted = true;
    const loadFedapayPolicySync = async () => {
      if (!showPaymentPicker || !selectedPlan?.id) {
        if (mounted) setFedapayPolicyUpdatedAt('');
        return;
      }
      try {
        const { data: fedapayPolicy } = await api.get('/subscriptions/mobile-money/fedapay-policy').catch(() => ({ data: null }));
        if (!mounted) return;
        setFedapayPolicyUpdatedAt(String(fedapayPolicy?.updated_at || ''));
      } catch {
        if (!mounted) return;
        setFedapayPolicyUpdatedAt('');
      }
    };
    loadFedapayPolicySync();
    return () => { mounted = false; };
  }, [showPaymentPicker, selectedPlan?.id]);

  useEffect(() => {
    let mounted = true;
    const loadGatewayConfig = async () => {
      if (!showPaymentPicker) return;
      try {
        const cfg = await fetchSubscriptionGatewayConfig();
        if (!mounted) return;
        setGatewayConfig(cfg);
      } catch {
        if (!mounted) return;
        setGatewayConfig(null);
      }
    };
    loadGatewayConfig();
    return () => { mounted = false; };
  }, [showPaymentPicker]);

  useEffect(() => {
    if (!showPaymentPicker) return;
    const intervalId = setInterval(() => setFedapaySyncClockMs(Date.now()), 60000);
    return () => clearInterval(intervalId);
  }, [showPaymentPicker]);

  const fedapayLastSyncedMinutes = getMinutesSinceIso(fedapayPolicyUpdatedAt, fedapaySyncClockMs);
  const fedapayLastSyncedLabel = fedapayLastSyncedMinutes == null
    ? tx('subscriptionPlans.paymentSync.pending', 'sync pending')
    : fedapayLastSyncedMinutes === 0
      ? tx('subscriptionPlans.paymentSync.justNow', 'just now')
      : `${fedapayLastSyncedMinutes} ${tx('subscriptionPlans.paymentSync.minute', fedapayLastSyncedMinutes === 1 ? 'minute' : 'minutes')} ${tx('subscriptionPlans.paymentSync.ago', 'ago')}`;
  const fedapaySyncTone = fedapayLastSyncedMinutes == null
    ? { border: C.border, bg: C.bgSoft, text: C.textMuted }
    : fedapayLastSyncedMinutes > 120
      ? { border: colors.errorSoft, bg: colors.errorSoft, text: colors.errorText }
      : fedapayLastSyncedMinutes > 30
        ? { border: colors.warningSoft, bg: colors.warningSoft, text: colors.warningText }
        : { border: colors.successSoft, bg: colors.successSoft, text: colors.successText };

  const availableMethods = useMemo(
    () => resolvePaymentMethodsFromGatewayConfig(gatewayConfig),
    [gatewayConfig],
  );

  const planColors = useMemo(() => ({
    free: C.textMuted,
    basic: C.primary,
    premium: colors.warningText,
  }), [C.primary, C.textMuted, colors.warningText]);

  const pickerStandardMethods = useMemo(() => ([
    {
      id: 'stripe' as const,
      title: tx('subscriptionPlans.methods.stripe.title', 'Stripe'),
      subtitle: tx('subscriptionPlans.methods.stripe.subtitle', 'Stripe (Cards, Apple Pay, Google Pay)'),
      iconName: 'card-outline' as const,
      iconColor: colors.indigoText,
      iconBg: colors.indigoSoft,
      testId: 'payment-stripe-btn',
      unavailableNoteTestId: 'payment-stripe-unavailable-note',
    },
    {
      id: 'paypal' as const,
      title: tx('subscriptionPlans.methods.paypal.title', 'PayPal'),
      subtitle: tx('subscriptionPlans.methods.paypal.subtitle', 'PayPal account or PayPal Credit'),
      iconName: 'logo-paypal' as const,
      iconColor: colors.info,
      iconBg: colors.infoSoft,
      testId: 'payment-paypal-btn',
      unavailableNoteTestId: 'payment-paypal-unavailable-note',
    },
    {
      id: 'apple_iap' as const,
      title: tx('subscriptionPlans.methods.appleIap.title', 'Apple IAP'),
      subtitle: tx('subscriptionPlans.methods.appleIap.subtitle', 'App Store in-app purchase handoff'),
      iconName: 'logo-apple' as const,
      iconColor: C.primary,
      iconBg: colors.primarySoft,
      testId: 'payment-apple-iap-btn',
      unavailableNoteTestId: 'payment-apple-iap-unavailable-note',
    },
    {
      id: 'google_iap' as const,
      title: tx('subscriptionPlans.methods.googleIap.title', 'Google IAP'),
      subtitle: tx('subscriptionPlans.methods.googleIap.subtitle', 'Google Play in-app purchase handoff'),
      iconName: 'logo-google-playstore' as const,
      iconColor: C.primary,
      iconBg: colors.primarySoft,
      testId: 'payment-google-iap-btn',
      unavailableNoteTestId: 'payment-google-iap-unavailable-note',
    },
  ]), [C.primary, colors.indigoText, colors.indigoSoft, colors.info, colors.infoSoft, colors.primarySoft, tx]);

  const isAdminForPicker = useMemo(() => {
    return Boolean(hasAdminFlag);
  }, [hasAdminFlag]);

  const pickerMobileMethods = useMemo(() => ([
    {
      id: 'fedapay' as const,
      title: tx('subscriptionPlans.methods.fedapay.title', 'FedaPay'),
      subtitle: tx('subscriptionPlans.methods.fedapay.subtitle', "FedaPay (Benin, Togo, Senegal, Côte d'Ivoire, Niger)"),
      iconName: 'cash-outline' as const,
      iconColor: colors.successText,
      iconBg: colors.successSoft,
      testId: 'payment-fedapay-btn',
      unavailableNoteTestId: 'payment-fedapay-unavailable-note',
      inlineNote: isAdminForPicker
        ? `${tx('subscriptionPlans.methods.fedapay.syncPrefix', 'Fees synced')} ${fedapayLastSyncedLabel}`
        : undefined,
    },
  ]), [colors.successSoft, colors.successText, fedapayLastSyncedLabel, isAdminForPicker, tx]);

  async function loadPlans() {
    try {
      const r = await api.get(`/subscriptions/plans?currency=${selectedCurrency}&lang=${languageCode || 'en'}`);
      setPlans((r.data.plans || []).map((plan: any) => ({
        ...plan,
        name: localizePlanLabel(plan.id || plan.plan_id, 'name', plan.name || ''),
        description: localizePlanLabel(plan.id || plan.plan_id, 'description', plan.description || ''),
        features: localizePlanArray(plan.id || plan.plan_id, 'features', plan.features || []),
        limitations: localizePlanArray(plan.id || plan.plan_id, 'limitations', plan.limitations || []),
      })));
      if (r.data.currency_symbol) setCurrencySymbol(r.data.currency_symbol);
      setModalToast(null);
    } catch (e) {
      handleAppRecoverableError({
        scope: 'subscription.plans.load-plans',
        error: e,
        message: tx('subscriptionPlans.errors.loadPlansFailed', 'Could not load subscription plans right now.'),
        onRetry: () => { void loadPlans(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setModalToast({
        type: 'error',
        message: tx('subscriptionPlans.errors.loadPlansFailed', 'Could not load subscription plans right now.'),
      });
    }
    finally { setLoading(false); }
  }

  const formatPrice = (price: number) => {
    if (price === 0) return `${currencySymbol}0`;
    if (ZERO_DECIMAL.has(selectedCurrency)) return `${currencySymbol}${Math.round(price).toLocaleString()}`;
    return `${currencySymbol}${price.toFixed(2)}`;
  };

  const sortedCurrencies = useMemo(() => {
    const popular = currencies.filter(c => POPULAR_CURRENCIES.includes(c.code))
      .sort((a, b) => POPULAR_CURRENCIES.indexOf(a.code) - POPULAR_CURRENCIES.indexOf(b.code));
    const rest = currencies.filter(c => !POPULAR_CURRENCIES.includes(c.code))
      .sort((a, b) => a.name.localeCompare(b.name));
    return [...popular, ...rest];
  }, [currencies]);

  const currentPlan = user?.subscription_plan || 'free';
  const isPaid = currentPlan !== 'free';
  const isCancelled = user?.subscription_status === 'cancelled';
  const isPrivileged = user?.full_access || hasAdminFlag;
  const isAdmin = hasAdminFlag;
  const [windowSearch, setWindowSearch] = useState('');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncSearch = () => {
      const next = window.location.search || '';
      setWindowSearch((prev) => (prev === next ? prev : next));
    };

    syncSearch();
    const intervalId = window.setInterval(syncSearch, 500);
    window.addEventListener('popstate', syncSearch);
    window.addEventListener('hashchange', syncSearch);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('popstate', syncSearch);
      window.removeEventListener('hashchange', syncSearch);
    };
  }, []);

  const webQueryParams = useMemo(() => new URLSearchParams(windowSearch || ''), [windowSearch]);

  const readSearchParam = useCallback((key: string) => {
    const localValue = (params as any)?.[key];
    if (Array.isArray(localValue) && localValue[0] != null) return String(localValue[0]);
    if (localValue != null && localValue !== '') return String(localValue);

    const globalValue = (globalParams as any)?.[key];
    if (Array.isArray(globalValue) && globalValue[0] != null) return String(globalValue[0]);
    if (globalValue != null && globalValue !== '') return String(globalValue);

    return String(webQueryParams.get(key) || '');
  }, [globalParams, params, webQueryParams]);

  const successParam = readSearchParam('success');
  const successPlanParam = readSearchParam('planId');
  const statusParam = readSearchParam('status').trim().toLowerCase();
  const cancelledParam = readSearchParam('cancelled').trim();
  const gatewayParam = readSearchParam('gateway').trim().toLowerCase();

  const sessionKey = useMemo(() => {
    const fallback = `subscription-session-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    if (Platform.OS !== 'web' || typeof window === 'undefined') return fallback;
    try {
      const storageKey = 'subscription_conversion_session_key_v1';
      const existing = window.sessionStorage.getItem(storageKey);
      if (existing) return existing;
      window.sessionStorage.setItem(storageKey, fallback);
      return fallback;
    } catch {
      return fallback;
    }
  }, []);

  const deviceBucket = useMemo(() => {
    if (sw < 768) return 'mobile';
    if (sw < 1100) return 'tablet';
    return 'desktop';
  }, [sw]);
  const plansPageSource = useMemo(() => buildAnalyticsSource('plans', 'page'), []);

  const trackConversionEvent = useCallback(async (eventType: 'plan_card_view' | 'plan_cta_click' | 'subscribe_success', planId?: string | null) => {
    try {
      await api.post('/subscription-conversion/telemetry', {
        session_key: sessionKey,
        event_type: eventType,
        plan_id: planId || undefined,
        billing_period: billingPeriod,
        role: isAdmin ? 'admin' : 'regular_user',
        device_bucket: deviceBucket,
        route: '/subscription/plans',
        source: plansPageSource,
      }, { silentLoading: true });
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/plans.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [billingPeriod, deviceBucket, isAdmin, plansPageSource, sessionKey]);

  const normalizeGatewayKey = useCallback((value: any): 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap' | 'unknown' => {
    const raw = String(value || '').trim().toLowerCase();
    if (raw.includes('paypal')) return 'paypal';
    if (raw.includes('feda') || raw.includes('mobile')) return 'fedapay';
    if (raw.includes('apple') || raw.includes('ios')) return 'apple_iap';
    if (raw.includes('google') || raw.includes('play')) return 'google_iap';
    if (raw.includes('stripe') || raw.includes('card')) return 'stripe';
    return 'unknown';
  }, []);

  const pushModalToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    setModalToast({ type, message });
  }, []);

  useEffect(() => {
    if (!modalToast) return;
    const timer = setTimeout(() => setModalToast(null), 2800);
    return () => clearTimeout(timer);
  }, [modalToast]);

  const loadPaymentDetails = useCallback(async (gatewayFilter: 'all' | 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap' = 'all') => {
    setPaymentDetailsLoading(true);
    try {
      const { data } = await api.get('/payments/history', {
        silentLoading: true,
        params: {
          ...(gatewayFilter !== 'all' ? { gateway: gatewayFilter } : {}),
          ...(appliedDetailDateFrom ? { start_date: appliedDetailDateFrom } : {}),
          ...(appliedDetailDateTo ? { end_date: appliedDetailDateTo } : {}),
        },
      });
      setPaymentDetails({
        payments: Array.isArray(data?.payments) ? data.payments : [],
        transactions: Array.isArray(data?.transactions) ? data.transactions : [],
      });
      setSelectedPaymentDetailIndex(0);
    } catch {
      setPaymentDetails({ payments: [], transactions: [] });
      setSelectedPaymentDetailIndex(0);
    } finally {
      setPaymentDetailsLoading(false);
    }
  }, [appliedDetailDateFrom, appliedDetailDateTo]);

  const handleCopyTransactionId = useCallback(async (rawId: any) => {
    const txId = String(rawId || '').trim();
    if (!txId) {
      Alert.alert('Unavailable', 'Transaction ID is not available for this row.');
      return;
    }
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(txId);
      } else {
        await Clipboard.setStringAsync(txId);
      }
      setCopiedTransactionId(txId);
      setTimeout(() => setCopiedTransactionId((prev) => (prev === txId ? '' : prev)), 2000);
    } catch {
      Alert.alert('Copy failed', 'Unable to copy transaction ID right now.');
    }
  }, []);

  const resolveReceiptDownloadId = useCallback((row: any): string => {
    const candidates = [
      row?.receipt_document_id,
      row?.payment_id,
      row?.transaction_id,
      row?.id,
      row?.session_id,
      row?.tx_id,
    ];
    for (const candidate of candidates) {
      const value = String(candidate || '').trim();
      if (value) return value;
    }
    return '';
  }, []);

  const downloadReceiptForRow = useCallback(async (row: any, rowIndex: number) => {
    const docId = resolveReceiptDownloadId(row);
    if (!docId) {
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.receiptUnavailableTitle', 'Receipt unavailable'),
        tx('subscriptionPlans.paymentDetails.receiptUnavailableMessage', 'No receipt identifier is available for this payment record.')
      );
      return;
    }

    const rowKey = `${docId}-${rowIndex}`;
    setDownloadingReceiptId(rowKey);
    try {
      const response = await api.get(`/payments/receipt/${encodeURIComponent(docId)}/pdf`, {
        responseType: 'blob',
        timeout: 45000,
        silentLoading: true,
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined' && response?.data) {
        const blobUrl = window.URL.createObjectURL(response.data as Blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = `receipt_${docId.slice(0, 12)}.pdf`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        window.URL.revokeObjectURL(blobUrl);
        pushModalToast('success', tx('subscriptionPlans.paymentDetails.receiptToastSuccess', 'Receipt download started successfully.'));
        return;
      }

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const fallback = String(row?.receipt_fallback_url || row?.receipt_download_url || '').trim();
        if (fallback) {
          window.open(fallback, '_blank', 'noopener,noreferrer');
          pushModalToast('success', tx('subscriptionPlans.paymentDetails.receiptToastSuccess', 'Receipt download started successfully.'));
          return;
        }
      }
      pushModalToast('success', tx('subscriptionPlans.paymentDetails.receiptToastSuccess', 'Receipt download started successfully.'));
    } catch {
      const fallback = String(row?.receipt_fallback_url || row?.receipt_download_url || '').trim();
      if (Platform.OS === 'web' && typeof window !== 'undefined' && fallback) {
        window.open(fallback, '_blank', 'noopener,noreferrer');
        pushModalToast('success', tx('subscriptionPlans.paymentDetails.receiptToastSuccess', 'Receipt download started successfully.'));
        return;
      }
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.receiptDownloadFailedTitle', 'Download failed'),
        tx('subscriptionPlans.paymentDetails.receiptDownloadFailedMessage', 'Unable to download the receipt right now. Please try again shortly.')
      );
    } finally {
      setDownloadingReceiptId((prev) => (prev === rowKey ? '' : prev));
    }
  }, [pushModalToast, resolveReceiptDownloadId, tx]);

  const downloadInvoiceForRow = useCallback(async (row: any, rowIndex: number) => {
    const docId = resolveReceiptDownloadId(row);
    if (!docId) {
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.invoiceUnavailableTitle', 'Invoice unavailable'),
        tx('subscriptionPlans.paymentDetails.invoiceUnavailableMessage', 'No invoice identifier is available for this payment record.')
      );
      return;
    }

    const rowKey = `${docId}-${rowIndex}`;
    setDownloadingInvoiceId(rowKey);
    try {
      const response = await api.get(`/payments/invoice/${encodeURIComponent(docId)}/pdf`, {
        responseType: 'blob',
        timeout: 45000,
        silentLoading: true,
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined' && response?.data) {
        const blobUrl = window.URL.createObjectURL(response.data as Blob);
        const anchor = document.createElement('a');
        anchor.href = blobUrl;
        anchor.download = `invoice_${docId.slice(0, 12)}.pdf`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        window.URL.revokeObjectURL(blobUrl);
        pushModalToast('success', tx('subscriptionPlans.paymentDetails.invoiceToastSuccess', 'Invoice download started successfully.'));
        return;
      }

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        const fallback = String(row?.invoice_download_url || '').trim();
        if (fallback) {
          window.open(fallback, '_blank', 'noopener,noreferrer');
          pushModalToast('success', tx('subscriptionPlans.paymentDetails.invoiceToastSuccess', 'Invoice download started successfully.'));
          return;
        }
      }
      pushModalToast('success', tx('subscriptionPlans.paymentDetails.invoiceToastSuccess', 'Invoice download started successfully.'));
    } catch {
      const fallback = String(row?.invoice_download_url || '').trim();
      if (Platform.OS === 'web' && typeof window !== 'undefined' && fallback) {
        window.open(fallback, '_blank', 'noopener,noreferrer');
        pushModalToast('success', tx('subscriptionPlans.paymentDetails.invoiceToastSuccess', 'Invoice download started successfully.'));
        return;
      }
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.invoiceDownloadFailedTitle', 'Download failed'),
        tx('subscriptionPlans.paymentDetails.invoiceDownloadFailedMessage', 'Unable to download the invoice right now. Please try again shortly.')
      );
    } finally {
      setDownloadingInvoiceId((prev) => (prev === rowKey ? '' : prev));
    }
  }, [pushModalToast, resolveReceiptDownloadId, tx]);

  const paymentDetailRows = useMemo(() => {
    const txRows = Array.isArray(paymentDetails.transactions) ? paymentDetails.transactions : [];
    const sourceRows = txRows.length > 0
      ? txRows
      : (Array.isArray(paymentDetails.payments) ? paymentDetails.payments : []);

    if (detailGatewayFilter === 'all') return sourceRows;
    return sourceRows.filter((row: any) => {
      const gatewayKey = String(row?.gateway_key || normalizeGatewayKey(row?.gateway || row?.provider || row?.payment_method)).toLowerCase();
      return gatewayKey === detailGatewayFilter;
    });
  }, [detailGatewayFilter, normalizeGatewayKey, paymentDetails.payments, paymentDetails.transactions]);

  const applyDetailDateRangeFilter = useCallback(() => {
    const normalizeDate = (raw: string) => raw.trim();
    const start = normalizeDate(detailDateFromInput);
    const end = normalizeDate(detailDateToInput);
    const datePattern = /^\d{4}-\d{2}-\d{2}$/;

    if (start && !datePattern.test(start)) {
      Alert.alert(tx('subscriptionPlans.paymentDetails.invalidDateTitle', 'Invalid start date'), tx('subscriptionPlans.paymentDetails.invalidDateMessage', 'Use YYYY-MM-DD format.'));
      return;
    }
    if (end && !datePattern.test(end)) {
      Alert.alert(tx('subscriptionPlans.paymentDetails.invalidDateTitle', 'Invalid end date'), tx('subscriptionPlans.paymentDetails.invalidDateMessage', 'Use YYYY-MM-DD format.'));
      return;
    }
    if (start && end && start > end) {
      Alert.alert(tx('subscriptionPlans.paymentDetails.invalidDateRangeTitle', 'Invalid date range'), tx('subscriptionPlans.paymentDetails.invalidDateRangeMessage', 'Start date must be before end date.'));
      return;
    }

    setAppliedDetailDateFrom(start);
    setAppliedDetailDateTo(end);
    setSelectedPaymentDetailIndex(0);
    pushModalToast('info', tx('subscriptionPlans.paymentDetails.dateFilterApplied', 'Date filter applied.'));
  }, [detailDateFromInput, detailDateToInput, pushModalToast, tx]);

  const clearDetailDateRangeFilter = useCallback(() => {
    setDetailDateFromInput('');
    setDetailDateToInput('');
    setAppliedDetailDateFrom('');
    setAppliedDetailDateTo('');
    setSelectedPaymentDetailIndex(0);
    pushModalToast('info', tx('subscriptionPlans.paymentDetails.dateFilterCleared', 'Date filter cleared.'));
  }, [pushModalToast, tx]);

  const bulkExportFilteredRows = useCallback(async (docType: 'receipt' | 'invoice') => {
    const paymentIds = Array.from(new Set(paymentDetailRows.map((row: any) => resolveReceiptDownloadId(row)).filter(Boolean)));
    if (!paymentIds.length) {
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.noRowsToExportTitle', 'Nothing to export'),
        tx('subscriptionPlans.paymentDetails.noRowsToExportMessage', 'No payment rows are available for the current filters.')
      );
      return;
    }

    setBulkExportingDocType(docType);
    try {
      const response = await api.post('/payments/bulk-export', {
        payment_ids: paymentIds,
        doc_type: docType,
      }, {
        responseType: 'blob',
        timeout: 60000,
        silentLoading: true,
      });

      if (Platform.OS === 'web' && typeof window !== 'undefined' && response?.data) {
        const blobUrl = window.URL.createObjectURL(response.data as Blob);
        const anchor = document.createElement('a');
        const dateSuffix = appliedDetailDateFrom || appliedDetailDateTo
          ? `${appliedDetailDateFrom || 'start'}_to_${appliedDetailDateTo || 'end'}`
          : 'all_dates';
        anchor.href = blobUrl;
        anchor.download = `${docType}s_${detailGatewayFilter}_filtered_${dateSuffix}.zip`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        window.URL.revokeObjectURL(blobUrl);
      }

      pushModalToast('success', tx('subscriptionPlans.paymentDetails.bulkExportSuccess', 'Bulk export download started.'));
    } catch {
      Alert.alert(
        tx('subscriptionPlans.paymentDetails.bulkExportFailedTitle', 'Bulk export failed'),
        tx('subscriptionPlans.paymentDetails.bulkExportFailedMessage', 'Unable to export filtered rows right now. Please try again.')
      );
    } finally {
      setBulkExportingDocType('');
    }
  }, [appliedDetailDateFrom, appliedDetailDateTo, detailGatewayFilter, paymentDetailRows, pushModalToast, resolveReceiptDownloadId, tx]);

  const feeText = useMemo(() => ({
    title: tx('fees.explainer.title', 'Why these fees?'),
    line1: tx('fees.explainer.line1', 'Base Subscription Price: the plan amount before taxes and payment handling fees.'),
    line2: tx('fees.explainer.line2', 'Applicable Tax: calculated from your checkout jurisdiction and provider policy.'),
    line3: tx('fees.explainer.line3', 'Payment Processing Fee: charged by the payment/store channel for handling the transaction.'),
    line4: tx('fees.explainer.line4', 'Total You Pay: Base Subscription Price + Applicable Tax + Payment Processing Fee.'),
  }), [tx]);

  const selectedPaymentDetailRow = useMemo(() => {
    if (!paymentDetailRows.length) return null;
    const safeIndex = Math.max(0, Math.min(selectedPaymentDetailIndex, paymentDetailRows.length - 1));
    return paymentDetailRows[safeIndex] || null;
  }, [paymentDetailRows, selectedPaymentDetailIndex]);

  const selectedProviderKey = useMemo(() => {
    return normalizeGatewayKey(
      selectedPaymentDetailRow?.gateway_key
      || selectedPaymentDetailRow?.gateway
      || selectedPaymentDetailRow?.provider
      || selectedPaymentDetailRow?.payment_method
      || ''
    );
  }, [normalizeGatewayKey, selectedPaymentDetailRow]);

  const selectedProviderLabel = useMemo(() => {
    if (selectedProviderKey === 'paypal') return 'PayPal';
    if (selectedProviderKey === 'fedapay') return 'FedaPay';
    if (selectedProviderKey === 'apple_iap') return 'Apple IAP';
    if (selectedProviderKey === 'google_iap') return 'Google IAP';
    if (selectedProviderKey === 'stripe') return 'Stripe';
    const raw = String(
      selectedPaymentDetailRow?.gateway
      || selectedPaymentDetailRow?.provider
      || selectedPaymentDetailRow?.payment_method
      || ''
    ).trim();
    return raw ? raw : tx('payment.feeTransparency.provider', 'Provider');
  }, [selectedPaymentDetailRow, selectedProviderKey, tx]);

  const formatDetailAmount = useCallback((value: any, row: any) => {
    const unavailable = tx('payment.feeTransparency.unavailableInRecord', 'Unavailable in record');
    if (value == null || value === '') return unavailable;
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return unavailable;
    const currency = String(row?.currency || selectedCurrency || 'USD').toUpperCase();
    const symbol = String(
      row?.currency_symbol
      || currencies.find((c) => c.code === currency)?.symbol
      || currencySymbol
      || '$'
    );
    const digits = ZERO_DECIMAL.has(currency) ? 0 : 2;
    return `${symbol} ${numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
  }, [currencies, currencySymbol, selectedCurrency, tx]);

  const selectedProviderFormula = useMemo(() => {
    if (!selectedPaymentDetailRow) return tx('payment.feeTransparency.unavailableInRecord', 'Unavailable in record');
    const explicit = String(
      selectedPaymentDetailRow?.processing_fee_formula
      || selectedPaymentDetailRow?.processing_fee_breakdown?.formula
      || ''
    ).trim();
    if (explicit) return explicit;
    const pct = Number(selectedPaymentDetailRow?.processing_fee_pct);
    if (Number.isFinite(pct) && pct > 0) return `${pct.toFixed(2)}%`;
    return tx('payment.feeTransparency.unavailableInRecord', 'Unavailable in record');
  }, [selectedPaymentDetailRow, tx]);

  const detailSummaryRows = useMemo(() => {
    if (!selectedPaymentDetailRow) return [];
    const jurisdiction = selectedPaymentDetailRow?.jurisdiction || {};
    const taxRatePct = Number(selectedPaymentDetailRow?.tax_rate || selectedPaymentDetailRow?.tax_rate_pct || 0);
    const safeTaxRatePct = Number.isFinite(taxRatePct)
      ? (taxRatePct <= 1 ? (taxRatePct * 100) : taxRatePct)
      : 0;

    const rows: any[] = [
      {
        key: 'subtotal',
        label: tx('payment.feeTransparency.baseSubscription', 'Base Subscription Price'),
        value: formatDetailAmount(selectedPaymentDetailRow?.subtotal, selectedPaymentDetailRow),
        glossaryKey: 'subtotal' as const,
        icon: 'cash-outline',
        tone: C.bgSoft,
      },
      {
        key: 'tax-fee',
        label: `${tx('payment.feeTransparency.applicableTax', 'Applicable Tax')} (${jurisdiction?.country || '-'}${jurisdiction?.state ? `-${jurisdiction.state}` : ''} @ ${safeTaxRatePct.toFixed(2)}%)`,
        value: formatDetailAmount(selectedPaymentDetailRow?.tax_amount, selectedPaymentDetailRow),
        glossaryKey: 'applicable_tax' as const,
        icon: 'receipt-outline',
        tone: C.bgSoft,
      },
      {
        key: 'processing-fee',
        label: `${tx('payment.feeTransparency.processingFee', 'Payment Processing Fee')} (${selectedProviderLabel})`,
        value: formatDetailAmount(selectedPaymentDetailRow?.processing_fee, selectedPaymentDetailRow),
        glossaryKey: 'processing_fee' as const,
        icon: 'flash-outline',
        tone: C.bgSoft,
      },
      {
        key: 'provider-formula',
        label: tx('payment.feeTransparency.providerFormula', 'Provider Fee Formula'),
        value: selectedProviderFormula,
        icon: 'construct-outline',
        tone: C.bgSoft,
      },
    ];

    return rows;
  }, [C.bgSoft, formatDetailAmount, selectedPaymentDetailRow, selectedProviderFormula, selectedProviderLabel, tx]);

  const detailProviderMetaRows = useMemo(() => {
    if (!selectedPaymentDetailRow) return [];
    return [
      {
        key: 'status',
        label: tx('subscriptionPlans.paymentDetails.status', 'Status'),
        value: String(selectedPaymentDetailRow?.status || 'unknown').toUpperCase(),
      },
      {
        key: 'tax-provider',
        label: tx('payment.feeTransparency.taxProvider', 'Tax Provider'),
        value: String(selectedPaymentDetailRow?.tax_provider || tx('payment.feeTransparency.unavailableInRecord', 'Unavailable in record')),
      },
    ];
  }, [selectedPaymentDetailRow, tx]);

  const detailLocalization = useMemo(() => {
    if (!selectedPaymentDetailRow) return null;
    const jurisdiction = selectedPaymentDetailRow?.jurisdiction || {};
    return {
      jurisdiction: `${jurisdiction?.country || '-'}${jurisdiction?.state ? `-${jurisdiction.state}` : ''}`,
      languageLabel: `${String(selectedPaymentDetailRow?.resolved_language || selectedPaymentDetailRow?.language || 'en').toUpperCase()}${selectedPaymentDetailRow?.localization_context?.confidence != null ? ` • Confidence: ${Math.round(Number(selectedPaymentDetailRow.localization_context.confidence) * 100)}%` : ''}`,
      fxLabel: selectedPaymentDetailRow?.fx_rate
        ? `FX: 1 USD = ${Number(selectedPaymentDetailRow.fx_rate).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${String(selectedPaymentDetailRow?.currency || selectedCurrency).toUpperCase()}`
        : tx('payment.feeTransparency.unavailableInRecord', 'Unavailable in record'),
    };
  }, [selectedCurrency, selectedPaymentDetailRow, tx]);

  useEffect(() => {
    if (!showPaymentDetailsModal) return;
    loadPaymentDetails(detailGatewayFilter);
  }, [detailGatewayFilter, loadPaymentDetails, showPaymentDetailsModal]);

  useEffect(() => {
    if (!isAdmin) {
      setConversionSummary(null);
      return;
    }

    let mounted = true;
    const loadSummary = async () => {
      if (!mounted) return;
      setConversionSummaryLoading(true);
      try {
        const { data } = await api.get('/admin/subscription-conversion/summary?hours=168&audience=real_users_only', { silentLoading: true });
        if (!mounted) return;
        setConversionSummary(data || null);
      } catch {
        if (!mounted) return;
        setConversionSummary(null);
      } finally {
        if (mounted) setConversionSummaryLoading(false);
      }
    };

    loadSummary();
    const intervalId = setInterval(loadSummary, 45000);
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [isAdmin]);

  useEffect(() => {
    if (!plans.length) return;
    plans.forEach((plan) => {
      const planId = String(plan?.id || '').trim();
      if (!planId) return;
      const key = `${planId}:${billingPeriod}`;
      if (trackedPlanViewsRef.current.has(key)) return;
      trackedPlanViewsRef.current.add(key);
      trackConversionEvent('plan_card_view', planId);
    });
  }, [billingPeriod, plans, trackConversionEvent]);

  useEffect(() => {
    if (String(successParam || '') !== '1') return;
    if (trackedSuccessRef.current) return;
    trackedSuccessRef.current = true;
    trackConversionEvent('subscribe_success', successPlanParam ? String(successPlanParam) : undefined);
  }, [successParam, successPlanParam, trackConversionEvent]);

  const returnStatusBanner = useMemo(() => {
    const normalizedStatus = statusParam || (String(successParam || '') === '1' ? 'success' : (cancelledParam ? 'cancelled' : ''));
    if (!normalizedStatus) {
      return null;
    }

    const gatewayStyles = {
      stripe: {
        label: 'Stripe',
        icon: 'card-outline' as const,
        accentBg: colors.indigoSoft,
        accentText: colors.indigoText,
      },
      paypal: {
        label: 'PayPal',
        icon: 'logo-paypal' as const,
        accentBg: colors.infoSoft,
        accentText: colors.info,
      },
      fedapay: {
        label: 'FedaPay',
        icon: 'cash-outline' as const,
        accentBg: colors.successSoft,
        accentText: colors.successText,
      },
      apple_iap: {
        label: 'Apple IAP',
        icon: 'logo-apple' as const,
        accentBg: colors.primarySoft,
        accentText: C.primary,
      },
      google_iap: {
        label: 'Google IAP',
        icon: 'logo-google-playstore' as const,
        accentBg: colors.primarySoft,
        accentText: C.primary,
      },
      generic: {
        label: tx('subscriptionPlans.banner.gateway.generic', 'Payment Gateway'),
        icon: 'wallet-outline' as const,
        accentBg: C.bgSoft,
        accentText: C.text,
      },
    };

    const gatewayStyle = gatewayStyles[gatewayParam as keyof typeof gatewayStyles] || gatewayStyles.generic;
    const gatewayLabel = gatewayStyle.label;
    const toneMap: Record<string, { tone: 'success' | 'warning' | 'error'; title: string; message: string }> = {
      success: {
        tone: 'success',
        title: tx('subscriptionPlans.banner.success.title', 'Payment completed'),
        message: tx('subscriptionPlans.banner.success.message', `${gatewayLabel} checkout succeeded. Your subscription updates are now active.`),
      },
      approved: {
        tone: 'success',
        title: tx('subscriptionPlans.banner.success.title', 'Payment completed'),
        message: tx('subscriptionPlans.banner.success.message', `${gatewayLabel} checkout succeeded. Your subscription updates are now active.`),
      },
      completed: {
        tone: 'success',
        title: tx('subscriptionPlans.banner.success.title', 'Payment completed'),
        message: tx('subscriptionPlans.banner.success.message', `${gatewayLabel} checkout succeeded. Your subscription updates are now active.`),
      },
      paid: {
        tone: 'success',
        title: tx('subscriptionPlans.banner.success.title', 'Payment completed'),
        message: tx('subscriptionPlans.banner.success.message', `${gatewayLabel} checkout succeeded. Your subscription updates are now active.`),
      },
      cancelled: getPaymentFailureCopy('cancelled', gatewayLabel, tx),
      canceled: getPaymentFailureCopy('cancelled', gatewayLabel, tx),
      declined: getPaymentFailureCopy('failed', gatewayLabel, tx),
      failed: getPaymentFailureCopy('failed', gatewayLabel, tx),
      refunded: getPaymentFailureCopy('refunded', gatewayLabel, tx),
      expired: getPaymentFailureCopy('expired', gatewayLabel, tx),
      unknown: getPaymentFailureCopy('unknown', gatewayLabel, tx),
    };

    const selected = toneMap[normalizedStatus] || (!['success', 'approved', 'completed', 'paid'].includes(normalizedStatus)
      ? getPaymentFailureCopy(normalizePaymentFailureState(normalizedStatus), gatewayLabel, tx)
      : null);
    if (!selected) return null;

    const key = `${normalizedStatus}:${gatewayParam || 'generic'}`;
    return { key, ...selected, gateway: gatewayStyle };
  }, [
    C.bgSoft,
    C.primary,
    C.text,
    cancelledParam,
    colors.indigoSoft,
    colors.indigoText,
    colors.info,
    colors.infoSoft,
    colors.primarySoft,
    colors.successSoft,
    colors.successText,
    gatewayParam,
    statusParam,
    successParam,
    tx,
  ]);

  const isReturnStatusBannerVisible = Boolean(
    returnStatusBanner
    && returnStatusBanner.key !== dismissedBannerKey
    && returnStatusBanner.key !== autoHiddenBannerKey
  );

  useEffect(() => {
    if (!returnStatusBanner || !isReturnStatusBannerVisible) return;
    if (returnStatusBanner.tone === 'success') return;
    notificationEvents.emit('toast', {
      title: returnStatusBanner.title,
      message: returnStatusBanner.message,
      type: returnStatusBanner.tone === 'error' ? 'payment_failed' : 'warning',
      actionLabel: tx('subscriptionPlans.banner.viewPaymentDetails', 'View payment details & fee transparency'),
      actionRoute: '/payment-history',
    });
  }, [isReturnStatusBannerVisible, returnStatusBanner, tx]);

  useEffect(() => {
    if (!returnStatusBanner) return;
    setAutoHiddenBannerKey('');
    const timeoutId = setTimeout(() => setAutoHiddenBannerKey(returnStatusBanner.key), 8000);
    return () => clearTimeout(timeoutId);
  }, [returnStatusBanner]);

  const handleSelectPlan = (plan: any) => {
    if (!isAuthenticated) {
      Alert.alert('Sign In Required', 'Please sign in to subscribe.', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign In', onPress: () => router.push('/auth/login') },
      ]);
      return;
    }
    if (plan.id === currentPlan) return;
    if (plan.id === 'free') { handleCancel(); return; }

    trackConversionEvent('plan_cta_click', String(plan.id || ''));
    setSelectedPlan(plan);
    setShowPaymentPicker(true);
  };

  const handlePaymentChoice = (method: 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap') => {
    if (!selectedPlan) return;
    const price = billingPeriod === 'monthly' ? selectedPlan.monthly_price : selectedPlan.yearly_price;
    api.post('/subscriptions/pricing-guard/frontend-event', {
      event_type: 'trust_checkout_conversion_click',
      plan_id: String(selectedPlan.id || ''),
      billing_period: billingPeriod,
      route: '/subscription/plans/payment-picker',
      payment_method: method,
      currency: selectedCurrency,
      canonical_price: Number(price),
      reason: 'payment_provider_selected',
    }, { silentLoading: true }).catch(() => {});
    setShowPaymentPicker(false);
    if (method === 'fedapay') {
      router.push({
        pathname: '/subscription/mobile-money',
        params: { planId: selectedPlan.id, planName: selectedPlan.name, planPrice: price.toString(), billingPeriod, provider: method, currency: 'XOF', return_to: resolvedUpgradeReturnTarget },
      });
    } else {
      router.push({
        pathname: '/subscription/payment',
        params: { planId: selectedPlan.id, planName: selectedPlan.name, planPrice: price.toString(), billingPeriod, paymentMethod: method, currency: selectedCurrency, return_to: resolvedUpgradeReturnTarget },
      });
    }
  };

  const handleCancel = () => {
    setCancelStep('reason');
    setCancelReason('');
    setCancelResult(null);
    setShowCancelModal(true);
  };

  const confirmCancel = async () => {
    setCancelling(true);
    try {
      const res = await api.post('/subscriptions/cancel', { reason: cancelReason });
      setCancelResult(res.data);
      setCancelStep('done');
      await refreshUser();
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to cancel subscription';
      setCancelResult({ error: msg });
      setCancelStep('done');
    } finally {
      setCancelling(false);
    }
  };

  const handleReactivate = async () => {
    try {
      setCancelling(true);
      await api.post('/subscriptions/reactivate');
      await refreshUser();
      setShowCancelModal(false);
    } catch (error) {
      handleAppRecoverableError({
        scope: 'subscription/plans.tsx#catch2',
        error,
        message: 'Something went wrong. Please retry.',
        notifyMode: 'dialog',
        userInitiated: true,
        onRetry: () => { void handleReactivate(); },
      });
    }
    setCancelling(false);
  };

  if (loading) return (
    <AppShell><SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <GallerySkeleton />
    </SafeAreaView></AppShell>
  );

  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }} edges={['top']}>
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: 40, paddingHorizontal: pageHorizontalPadding }}
          data-testid="subscription-plans-screen"
          testID="subscription-plans-screen"
          onLayout={(event) => {
            const nextWidth = Math.max(320, Math.round(event.nativeEvent.layout.width || 0));
            setPlansContentWidth((prev) => (prev === nextWidth ? prev : nextWidth));
          }}
        >

          <View style={{ marginTop: 8, marginBottom: 18 }} data-testid="subscription-plans-hero" testID="subscription-plans-hero">
            {!!contextualUpgradeCopy && (
              <View
                style={{
                  marginBottom: 12,
                  borderRadius: 18,
                  borderWidth: 1,
                  borderColor: `${C.primary}44`,
                  backgroundColor: `${C.primary}13`,
                  padding: 14,
                  gap: 8,
                }}
                data-testid="subscription-contextual-upgrade-banner"
                testID="subscription-contextual-upgrade-banner"
              >
                <View
                  style={{
                    alignSelf: 'flex-start',
                    paddingHorizontal: 10,
                    paddingVertical: 5,
                    borderRadius: 999,
                    backgroundColor: `${C.primary}20`,
                  }}
                  data-testid="subscription-contextual-upgrade-pill"
                  testID="subscription-contextual-upgrade-pill"
                >
                  <Text style={[{ color: C.primary, fontSize: 10, fontWeight: '800', letterSpacing: 0.6 }, bodyFont || {}]} data-testid="subscription-contextual-upgrade-pill-text" testID="subscription-contextual-upgrade-pill-text">
                    {contextualUpgradeEyebrow}
                  </Text>
                </View>
                <Text style={[{ color: C.text, fontSize: 13, fontWeight: '800' }, bodyFont || {}]} data-testid="subscription-contextual-upgrade-title" testID="subscription-contextual-upgrade-title">
                  {contextualUpgradeTitle}
                </Text>
                <Text style={[{ color: C.textSec, fontSize: 12, lineHeight: 18 }, bodyFont || {}]} data-testid="subscription-contextual-upgrade-benefit" testID="subscription-contextual-upgrade-benefit">
                  {contextualUpgradeCopy.benefit}
                </Text>
                <Text style={[{ color: C.primary, fontSize: 11, fontWeight: '700' }, bodyFont || {}]} data-testid="subscription-contextual-upgrade-meta" testID="subscription-contextual-upgrade-meta">
                  {contextualUpgradeMeta}
                </Text>
              </View>
            )}

            <ImageBackground
              source={{ uri: heroImageUri }}
              style={{ borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: C.borderStrong, backgroundColor: C.surfaceElevated }}
              imageStyle={{ opacity: darkMode ? 0.34 : 0.24 }}
              data-testid="subscription-plans-hero-image"
              testID="subscription-plans-hero-image"
            >
              <View style={{ backgroundColor: heroOverlayColor, paddingHorizontal: responsiveWidth >= 1180 ? 30 : responsiveWidth >= 760 ? 24 : 18, paddingTop: 18, paddingBottom: 22 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
                  <TouchableOpacity
                    style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: heroControlSurface, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.borderStrong }}
                    onPress={() => router.back()}
                    data-testid="plans-back-btn"
                    testID="plans-back-btn"
                  >
                    <Ionicons name="arrow-back" size={20} color={C.text} />
                  </TouchableOpacity>
                  <View style={{ width: 1 }} />
                </View>

                <Text style={[{ color: C.text, fontSize: responsiveWidth >= 1180 ? 42 : responsiveWidth >= 760 ? 36 : 30, fontWeight: '700', lineHeight: responsiveWidth >= 1180 ? 46 : responsiveWidth >= 760 ? 40 : 35, letterSpacing: -1.2, maxWidth: responsiveWidth >= 1180 ? 700 : undefined }, headingFont || {}]} data-testid="plans-hero-title" testID="plans-hero-title">
                  {tx('subscriptionPlans.hero.title', 'Enterprise-Grade')}
                </Text>
                <Text style={[{ color: C.textSec, fontSize: responsiveWidth >= 1180 ? 16 : 13, marginTop: 10, lineHeight: 23, maxWidth: responsiveWidth >= 1180 ? 620 : undefined }, bodyFont || {}]} data-testid="plans-hero-subtitle" testID="plans-hero-subtitle">
                  {tx('subscriptionPlans.hero.subtitle', 'Choose the plan that scales with your growth and move to Subscribe & Pay in one step.')}
                </Text>

                <View style={[{ marginTop: 18, gap: 10 }, !stackHeroControls ? { flexDirection: 'row', alignItems: 'center' } : null]}>
                  <View style={{ flex: 1, flexDirection: 'row', borderRadius: 999, borderWidth: 1, borderColor: C.borderStrong, padding: 4, backgroundColor: heroControlSurface }} data-testid="plans-billing-segmented-control" testID="plans-billing-segmented-control">
                    {['monthly', 'yearly'].map((p) => (
                      <TouchableOpacity
                        key={p}
                        style={{
                          flex: 1,
                          flexDirection: 'row',
                          alignItems: 'center',
                          justifyContent: 'center',
                          paddingVertical: 11,
                          borderRadius: 999,
                          gap: 6,
                          backgroundColor: billingPeriod === p ? C.surfaceElevated : 'transparent',
                          borderWidth: billingPeriod === p ? 1 : 0,
                          borderColor: billingPeriod === p ? C.borderStrong : 'transparent',
                        }}
                        onPress={() => setBillingPeriod(p)}
                        data-testid={`billing-toggle-${p}`}
                        testID={`billing-toggle-${p}`}
                      >
                        <Text style={[{ fontWeight: '700', color: billingPeriod === p ? C.text : C.textMuted, fontSize: 12 }, bodyFont || {}]}>
                          {p === 'monthly' ? tx('subscriptionPlans.billing.monthly', 'Monthly') : tx('subscriptionPlans.billing.yearly', 'Yearly')}
                        </Text>
                        {p === 'yearly' && (
                          <View style={{ backgroundColor: colors.successSoft, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: colors.successSoft }} data-testid="plans-yearly-save-badge" testID="plans-yearly-save-badge">
                            <Text style={[{ color: colors.successText, fontWeight: '800', fontSize: 10 }, bodyFont || {}]}>{yearlySaveBadgeText}</Text>
                          </View>
                        )}
                      </TouchableOpacity>
                    ))}
                  </View>

                  <TouchableOpacity
                    onPress={() => setShowCurrencyPicker(true)}
                    style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minWidth: !stackHeroControls ? 170 : undefined, borderRadius: 999, borderWidth: 1, borderColor: C.borderStrong, backgroundColor: heroControlSurface, paddingHorizontal: 14, paddingVertical: 11 }}
                    data-testid="plans-currency-selector"
                    testID="plans-currency-selector"
                  >
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
                      <Ionicons name="globe-outline" size={15} color={C.primary} />
                      <Text style={[{ color: C.text, fontSize: 12, fontWeight: '700' }, bodyFont || {}]}>{selectedCurrency}</Text>
                    </View>
                    <Ionicons name="chevron-down" size={12} color={C.textMuted} />
                  </TouchableOpacity>
                </View>

                <View
                  style={{
                    marginTop: 12,
                    alignSelf: 'flex-start',
                    flexDirection: 'row',
                    flexWrap: 'wrap',
                    gap: 8,
                    padding: 6,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: C.borderStrong,
                    backgroundColor: heroControlSurface,
                  }}
                  data-testid="plans-theme-mode-control"
                  testID="plans-theme-mode-control"
                >
                  {([
                    { key: 'light', label: tx('common.themeLight', 'Light'), icon: 'sunny-outline' },
                    { key: 'system', label: tx('common.themeSystem', 'System'), icon: 'desktop-outline' },
                    { key: 'dark', label: tx('common.themeDark', 'Dark'), icon: 'moon-outline' },
                  ] as const).map((option) => {
                    const isActive = themeMode === option.key;
                    return (
                      <TouchableOpacity
                        key={option.key}
                        onPress={() => setThemeMode(option.key)}
                        style={{
                          flexDirection: 'row',
                          alignItems: 'center',
                          gap: 6,
                          borderRadius: 999,
                          paddingHorizontal: 12,
                          paddingVertical: 8,
                          borderWidth: 1,
                          borderColor: isActive ? C.primary : 'transparent',
                          backgroundColor: isActive ? withAlpha(C.primary, darkMode ? '20' : '14') : 'transparent',
                        }}
                        data-testid={`plans-theme-mode-${option.key}`}
                        testID={`plans-theme-mode-${option.key}`}
                      >
                        <Ionicons name={option.icon as any} size={14} color={isActive ? C.primary : C.textMuted} />
                        <Text style={[{ color: isActive ? C.primary : C.text, fontSize: 12, fontWeight: '800' }, bodyFont || {}]}>{option.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            </ImageBackground>
          </View>

          {returnStatusBanner && isReturnStatusBannerVisible && (
            <View
              style={{
                borderRadius: 12,
                borderWidth: 1,
                borderColor: returnStatusBanner.tone === 'success' ? colors.successSoft : returnStatusBanner.tone === 'warning' ? colors.warningSoft : colors.errorSoft,
                backgroundColor: returnStatusBanner.tone === 'success' ? colors.successSoft : returnStatusBanner.tone === 'warning' ? colors.warningSoft : colors.errorSoft,
                paddingHorizontal: 12,
                paddingVertical: 11,
                marginBottom: 14,
                flexDirection: 'row',
                alignItems: 'flex-start',
                gap: 10,
              }}
              data-testid="plans-return-status-banner"
              testID="plans-return-status-banner"
            >
              <Ionicons
                name={returnStatusBanner.gateway.icon}
                size={18}
                color={returnStatusBanner.gateway.accentText}
              />
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Text
                    style={{
                      color: returnStatusBanner.gateway.accentText,
                      fontWeight: '800',
                      fontSize: 12,
                    }}
                    data-testid="plans-return-status-banner-title"
                    testID="plans-return-status-banner-title"
                  >
                    {returnStatusBanner.title}
                  </Text>
                  <View
                    style={{
                      borderRadius: 999,
                      paddingHorizontal: 8,
                      paddingVertical: 2,
                      borderWidth: 1,
                      borderColor: returnStatusBanner.gateway.accentBg,
                      backgroundColor: returnStatusBanner.gateway.accentBg,
                    }}
                    data-testid="plans-return-status-banner-gateway-chip"
                    testID="plans-return-status-banner-gateway-chip"
                  >
                    <Text style={{ color: returnStatusBanner.gateway.accentText, fontSize: 10, fontWeight: '700' }}>
                      {returnStatusBanner.gateway.label}
                    </Text>
                  </View>
                </View>
                <Text
                  style={{ color: C.textSec, fontSize: 11, marginTop: 2, lineHeight: 17 }}
                  data-testid="plans-return-status-banner-message"
                  testID="plans-return-status-banner-message"
                >
                  {returnStatusBanner.message}
                </Text>
                <TouchableOpacity
                  onPress={() => {
                    const bannerGateway = normalizeGatewayKey(gatewayParam || '');
                    setDetailGatewayFilter(bannerGateway === 'unknown' ? 'all' : bannerGateway);
                    setDetailDateFromInput('');
                    setDetailDateToInput('');
                    setAppliedDetailDateFrom('');
                    setAppliedDetailDateTo('');
                    setModalToast(null);
                    setShowPaymentDetailsModal(true);
                  }}
                  style={{ marginTop: 6, alignSelf: 'flex-start' }}
                  data-testid="plans-return-status-banner-view-details-link"
                  testID="plans-return-status-banner-view-details-link"
                >
                  <Text style={{ color: returnStatusBanner.gateway.accentText, fontSize: 11, fontWeight: '700', textDecorationLine: 'underline' }}>
                    {tx('subscriptionPlans.banner.viewPaymentDetails', 'View payment details & fee transparency')}
                  </Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity
                onPress={() => {
                  setDismissedBannerKey(returnStatusBanner.key);
                }}
                style={{ width: 22, height: 22, borderRadius: 11, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border, backgroundColor: C.card }}
                data-testid="plans-return-status-banner-close"
                testID="plans-return-status-banner-close"
              >
                <Ionicons name="close" size={13} color={C.textMuted} />
              </TouchableOpacity>
            </View>
          )}

          {/* Current subscription status for paid users */}
          {isAuthenticated && isPaid && (
            <View style={{ backgroundColor: C.surfaceElevated, borderRadius: 18, borderWidth: 1, borderColor: C.borderStrong, padding: 20, marginBottom: 20 }} data-testid="current-plan-card" testID="current-plan-card">
              <View style={{ flexDirection: isPhone ? 'column' : 'row', alignItems: isPhone ? 'flex-start' : 'center', gap: 12, marginBottom: 14 }}>
                <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: withAlpha(planColors[currentPlan as keyof typeof planColors] || C.primary, '22'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={(PLAN_ICONS[currentPlan as keyof typeof PLAN_ICONS] || 'person') as any} size={22} color={planColors[currentPlan as keyof typeof planColors] || C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[{ fontSize: 18, fontWeight: '800', color: C.text }, headingFont || {}]} data-testid="current-plan-title" testID="current-plan-title">{tx(`subscriptionPlans.plan.${currentPlan}.name`, currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1))} {tx('subscriptionPlans.currentPlan', 'Plan')}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 }}>
                    <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: isCancelled ? colors.error : colors.success }} />
                    <Text style={[{ color: C.textSec, fontSize: 12, fontWeight: '600' }, bodyFont || {}]}>{isCancelled ? tx('subscriptionPlans.status.cancelling', 'Cancelling') : tx('subscriptionPlans.status.active', 'Active')}</Text>
                  </View>
                </View>
                <SubscriptionBadge plan={currentPlan} size="lg" showLabel={false} />
              </View>
              {!isCancelled && !isPrivileged && (
                <TouchableOpacity onPress={handleCancel} disabled={cancelling} style={{ backgroundColor: colors.errorSoft, paddingVertical: 10, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: withAlpha(colors.errorText, '2A') }} data-testid="cancel-subscription-btn" testID="cancel-subscription-btn">
                  {cancelling ? <ActivityIndicator color={colors.errorText} size="small" /> : <Text style={[{ color: colors.errorText, fontWeight: '700', fontSize: 13 }, bodyFont || {}]}>{tx('subscriptionPlans.actions.cancelSubscription', 'Cancel Subscription')}</Text>}
                </TouchableOpacity>
              )}
            </View>
          )}

          {isAdmin && (
            <View
              style={{
                backgroundColor: C.card,
                borderRadius: 16,
                borderWidth: 1,
                borderColor: C.border,
                padding: 16,
                marginBottom: 18,
              }}
              data-testid="plans-conversion-summary-card"
              testID="plans-conversion-summary-card"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <Text style={[{ color: C.text, fontSize: 16, fontWeight: '800' }, headingFont || {}]} data-testid="plans-conversion-summary-title" testID="plans-conversion-summary-title">
                  {tx('subscriptionPlans.admin.conversionTracker', 'Plan Conversion Tracker (7d)')}
                </Text>
                <View
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: withAlpha(colors.successText, '55'), backgroundColor: withAlpha(colors.successText, '14'), paddingHorizontal: 8, paddingVertical: 4 }}
                  data-testid="plans-conversion-audience-chip"
                  testID="plans-conversion-audience-chip"
                >
                  <Text style={{ color: colors.successText, fontSize: 10, fontWeight: '800' }}>
                    {tx('subscriptionPlans.admin.realUsersOnly', 'Real users only')}
                  </Text>
                </View>
                {conversionSummaryLoading ? <ActivityIndicator size="small" color={C.primary} /> : null}
              </View>

              {conversionSummary ? (
                <>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
                    {[
                      { key: 'views', label: tx('subscriptionPlans.admin.views', 'Views'), value: conversionSummary?.funnel?.plan_card_view || 0 },
                      { key: 'clicks', label: tx('subscriptionPlans.admin.ctaClicks', 'CTA Clicks'), value: conversionSummary?.funnel?.plan_cta_click || 0 },
                      { key: 'success', label: tx('subscriptionPlans.admin.success', 'Success'), value: conversionSummary?.funnel?.subscribe_success || 0 },
                      { key: 'ctr', label: tx('subscriptionPlans.admin.ctr', 'CTR'), value: `${Number(conversionSummary?.funnel?.click_through_rate || 0).toFixed(2)}%` },
                      { key: 'csr', label: tx('subscriptionPlans.admin.successRate', 'Success Rate'), value: `${Number(conversionSummary?.funnel?.checkout_success_rate || 0).toFixed(2)}%` },
                    ].map((metric) => (
                      <View
                        key={metric.key}
                        style={{ backgroundColor: C.bgSoft, borderRadius: 10, borderWidth: 1, borderColor: C.border, paddingVertical: 9, paddingHorizontal: 10, minWidth: isWide ? 118 : '48%' as any }}
                        data-testid={`plans-conversion-metric-${metric.key}`}
                        testID={`plans-conversion-metric-${metric.key}`}
                      >
                        <Text style={[{ color: C.textMuted, fontSize: 10, fontWeight: '700' }, bodyFont || {}]}>{metric.label}</Text>
                        <Text style={[{ color: C.text, fontSize: 15, fontWeight: '800', marginTop: 2 }, headingFont || {}]}>{metric.value}</Text>
                      </View>
                    ))}
                  </View>

                  <View style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="plans-conversion-top-plans" testID="plans-conversion-top-plans">
                    {(conversionSummary?.by_plan || []).slice(0, 3).map((row: any, idx: number) => (
                      <View
                        key={`${row?.plan_id || 'unknown'}-${idx}`}
                        style={{
                          flexDirection: 'row',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          paddingVertical: 9,
                          paddingHorizontal: 10,
                          borderTopWidth: idx === 0 ? 0 : 1,
                          borderTopColor: C.border,
                          backgroundColor: idx % 2 === 0 ? C.card : C.bgSoft,
                        }}
                        data-testid={`plans-conversion-row-${idx}`}
                        testID={`plans-conversion-row-${idx}`}
                      >
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' }}>{tx(`subscriptionPlans.plan.${row?.plan_id}.name`, row?.plan_id || 'unknown')}</Text>
                        <Text style={{ color: C.textSec, fontSize: 11 }}>{tx('subscriptionPlans.admin.viewsShort', 'V')}:{row?.views || 0} · {tx('subscriptionPlans.admin.clicksShort', 'C')}:{row?.clicks || 0} · {tx('subscriptionPlans.admin.successShort', 'S')}:{row?.success || 0}</Text>
                      </View>
                    ))}
                    {!(conversionSummary?.by_plan || []).length ? (
                      <View style={{ paddingVertical: 10, paddingHorizontal: 10 }}>
                        <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="plans-conversion-no-data" testID="plans-conversion-no-data">
                          {tx('subscriptionPlans.admin.noConversionEvents', 'No conversion events yet in the selected window.')}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={{ color: C.textMuted, fontSize: 10.5, marginTop: 8 }} data-testid="plans-conversion-filter-note" testID="plans-conversion-filter-note">
                    {tx('subscriptionPlans.admin.filterNote', 'Excludes admin traffic and test domains (example/localhost/local + e2e/test/qa/dev prefixes).')}
                  </Text>
                </>
              ) : (
                <Text style={{ color: C.textMuted, fontSize: 12 }} data-testid="plans-conversion-summary-empty" testID="plans-conversion-summary-empty">
                  Conversion summary unavailable right now.
                </Text>
              )}
            </View>
          )}

          {/* Plan Cards */}
          <View
            style={[
              { gap: planGridGap },
              planColumnCount > 1
                  ? { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'stretch' }
                : null,
            ]}
            data-testid="subscription-plans-grid"
            testID="subscription-plans-grid"
          >
            {plans.map(plan => {
              const price = billingPeriod === 'monthly' ? plan.monthly_price : plan.yearly_price;
              const isCurrent = plan.id === currentPlan;
              const isUpgrade = isPaid && plan.id === 'premium' && currentPlan === 'basic';
              const isPremiumPlan = plan.id === 'premium';
              const color = planColors[plan.id as keyof typeof planColors] || C.textMuted;

              return (
                <View
                  key={plan.id}
                  style={[
                    {
                      backgroundColor: C.surfaceElevated,
                      borderRadius: 20,
                      padding: responsiveWidth >= 760 ? 24 : 18,
                      borderWidth: isCurrent ? 1.8 : 1,
                      borderColor: isCurrent ? color : C.borderStrong,
                      position: 'relative' as const,
                      minHeight: planColumnCount > 1 ? 430 : undefined,
                      overflow: 'hidden' as const,
                    },
                    planColumnCount === 1 ? null : { width: planCardWidth },
                  ]}
                  data-testid={`plan-card-${plan.id}`}
                  testID={`plan-card-${plan.id}`}
                >
                  {isPremiumPlan && (
                    <View style={{ position: 'absolute', top: 14, right: 14, flexDirection: 'row', alignItems: 'center', backgroundColor: premiumBadgeSurface, borderWidth: 1, borderColor: premiumBadgeBorder, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, gap: 4, zIndex: 1 }} data-testid={`plan-recommended-badge-${plan.id}`} testID={`plan-recommended-badge-${plan.id}`}>
                      <Ionicons name="sparkles" size={11} color={colors.warningText} />
                      <Text style={[{ fontWeight: '800', color: colors.warningText, fontSize: 10, letterSpacing: 0.7 }, bodyFont || {}]}>{tx('subscriptionPlans.actions.recommended', 'RECOMMENDED')}</Text>
                    </View>
                  )}

                  {/* Badge Preview */}
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                      <View style={{ width: 42, height: 42, borderRadius: 12, backgroundColor: withAlpha(color, darkMode ? '24' : '16'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={(PLAN_ICONS[plan.id as keyof typeof PLAN_ICONS] || 'person') as any} size={20} color={color} />
                      </View>
                      <View>
                        <Text style={[{ fontWeight: '700', color: C.text, fontSize: 18 }, headingFont || {}]} data-testid={`plan-name-${plan.id}`} testID={`plan-name-${plan.id}`}>{plan.name}</Text>
                        <Text style={[{ color: C.textMuted, fontSize: 12, marginTop: 2, lineHeight: 18 }, bodyFont || {}]} data-testid={`plan-description-${plan.id}`} testID={`plan-description-${plan.id}`}>{plan.description}</Text>
                      </View>
                    </View>
                    <SubscriptionBadge plan={plan.id} size="sm" />
                  </View>

                  {/* Price */}
                  <View style={{ flexDirection: 'row', alignItems: 'baseline', marginBottom: 16 }}>
                    <Text style={[{ fontWeight: '800', color: C.text, fontSize: 34, letterSpacing: -0.8 }, headingFont || {}]} data-testid={`plan-price-${plan.id}`} testID={`plan-price-${plan.id}`}>{formatPrice(price)}</Text>
                    <Text style={[{ color: C.textMuted, fontSize: 13, marginLeft: 3 }, bodyFont || {}]} data-testid={`plan-period-${plan.id}`} testID={`plan-period-${plan.id}`}>/{billingPeriod === 'monthly' ? 'mo' : 'yr'}</Text>
                  </View>

                  {/* Features */}
                  {plan.features?.map((f: string, i: number) => (
                    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <Ionicons name="checkmark-circle" size={16} color={C.successText} />
                      <Text style={[{ color: C.textSec, fontSize: 13, flex: 1, lineHeight: 21 }, bodyFont || {}]}>{f}</Text>
                    </View>
                  ))}

                  {/* Limitations */}
                  {plan.limitations?.length > 0 && (
                    <View style={{ marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: C.border }}>
                      {plan.limitations.map((l: string, i: number) => (
                        <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                          <Ionicons name="close-circle" size={14} color={C.error + '80'} />
                          <Text style={[{ color: C.textMuted, fontSize: 12, flex: 1, lineHeight: 18 }, bodyFont || {}]}>{l}</Text>
                        </View>
                      ))}
                    </View>
                  )}

                  {/* CTA Button */}
                  <TouchableOpacity
                    style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: 12, marginTop: 16, backgroundColor: isCurrent ? C.bgSoft : C.primary, opacity: isCurrent ? 0.7 : 1, borderWidth: 1, borderColor: isCurrent ? C.border : C.primary }}
                    onPress={() => handleSelectPlan(plan)}
                    disabled={isCurrent}
                    data-testid={`plan-cta-${plan.id}`} testID={`plan-cta-${plan.id}`}
                  >
                    <Text style={[{ fontWeight: '800', color: isCurrent ? C.textMuted : colors.primaryText, fontSize: 14, letterSpacing: 0.3 }, bodyFont || {}]}>
                      {isCurrent
                        ? tx('subscriptionPlans.actions.currentPlan', 'Current Plan')
                        : isUpgrade
                          ? tx('subscriptionPlans.actions.upgradeNow', 'Upgrade Now')
                          : plan.id === 'free'
                            ? tx('subscriptionPlans.actions.downgrade', 'Downgrade')
                            : tx('subscriptionPlans.actions.subscribeAndPay', 'Subscribe & Pay')}
                    </Text>
                  </TouchableOpacity>

                  {isCurrent && isAdmin ? (
                    <TouchableOpacity
                      style={{ alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 10, marginTop: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt }}
                      onPress={() => { setSelectedPlan(plan); setShowPaymentPicker(true); }}
                      data-testid={`plan-payment-options-${plan.id}`} testID={`plan-payment-options-${plan.id}`}
                    >
                      <Text style={{ fontWeight: '600', color: C.textSec, fontSize: 12 }}>{t("autofix.watchSweep1.view.payment.methods.tax.jurisdiction")}</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
              );
            })}
          </View>

          {/* Help */}
          <View style={{ marginTop: 24 }}>
            <TouchableOpacity style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 14, gap: 12, borderBottomWidth: 1, borderBottomColor: C.border }} onPress={() => router.push('/help')} data-testid="plans-help-btn" testID="plans-help-btn">
              <Ionicons name="help-circle-outline" size={18} color={C.primary} />
              <Text style={{ flex: 1, fontWeight: '500', color: C.primary, fontSize: 13 }}>{t("autofix.watchSweep1.need.help.contact.support")}</Text>
              <Ionicons name="chevron-forward" size={16} color={C.textMuted} />
            </TouchableOpacity>
          </View>

          <View style={{ alignItems: 'center', paddingTop: 16 }}>
            <Text style={{ color: C.textMuted, fontSize: 11 }}>{t("autofix.watchSweep1.subscriptions.auto.renew.cancel.anytime")}</Text>
            <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }}>{'\u00A9'}{t("autofix.watchSweep1.2026.2030.realaicoach.llc.all.rights.reserved.usa")}</Text>
          </View>
        </ScrollView>

        {/* ═══ CANCEL SUBSCRIPTION MODAL ═══ */}
        <Modal visible={showCancelModal} transparent animationType="fade" data-testid="cancel-subscription-modal" testID="cancel-subscription-modal">
          <View style={StyleSheet.absoluteFillObject}>
            <TouchableOpacity style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => !cancelling && setShowCancelModal(false)} activeOpacity={1} />
            <View style={{ position: 'absolute', top: '15%', left: isWide ? '30%' : 20, right: isWide ? '30%' : 20, backgroundColor: C.card, borderRadius: 20, padding: 24, maxHeight: '70%' }}>
              {cancelStep === 'reason' && (
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="warning" size={22} color={colors.error} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }} data-testid="cancel-modal-title" testID="cancel-modal-title">{t("subscriptionPlans.actions.cancelSubscription")}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 2 }}>{t("autofix.watchSweep1.we.re.sorry.to.see.you.go")}</Text>
                    </View>
                  </View>
                  <Text style={{ color: C.text, fontSize: 13, lineHeight: 20, marginBottom: 12 }}>{t("autofix.watchSweep1.your")}{currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1)}{t("autofix.watchSweep1.plan.benefits.will.continue.until.the.end.of")}</Text>
                  <View style={{ backgroundColor: C.bgSoft, borderRadius: 12, padding: 12, marginBottom: 16 }}>
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }}>{t("autofix.watchSweep1.what.you.ll.lose")}</Text>
                    {(currentPlan === 'premium' ? ['All active AI copilots', 'Priority support', 'Advanced analytics', 'Unlimited coaching sessions'] : ['Basic AI tools access', 'Standard support']).map((item, i) => (
                      <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Ionicons name="close-circle" size={14} color={colors.error} />
                        <Text style={{ color: C.textMuted, fontSize: 12 }}>{item}</Text>
                      </View>
                    ))}
                  </View>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 8 }}>{t("autofix.watchSweep1.help.us.improve.why.are.you.cancelling")}</Text>
                  <TextInput
                    data-testid="cancel-reason-input" testID="cancel-reason-input"
                    value={cancelReason}
                    onChangeText={setCancelReason}
                    placeholder="Too expensive, not enough content, found alternative..."
                    placeholderTextColor={C.textMuted}
                    multiline
                    style={{ backgroundColor: C.bgSoft, borderRadius: 10, padding: 12, color: C.text, fontSize: 13, minHeight: 70, borderWidth: 1, borderColor: C.border, textAlignVertical: 'top' } as any}
                  />
                  <View style={{ flexDirection: 'row', gap: 10, marginTop: 20 }}>
                    <TouchableOpacity
                      data-testid="keep-subscription-btn" testID="keep-subscription-btn"
                      onPress={() => setShowCancelModal(false)}
                      style={{ flex: 1, backgroundColor: C.primary, paddingVertical: 12, borderRadius: 10, alignItems: 'center' }}
                    >
                      <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{t("autofix.watchSweep1.keep.my.plan")}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      data-testid="proceed-cancel-btn" testID="proceed-cancel-btn"
                      onPress={() => setCancelStep('confirm')}
                      style={{ flex: 1, backgroundColor: 'transparent', paddingVertical: 12, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: colors.error }}
                    >
                      <Text style={{ color: colors.error, fontWeight: '700', fontSize: 14 }}>{t("welcomeBack.continue")}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {cancelStep === 'confirm' && (
                <View>
                  <View style={{ alignItems: 'center', marginBottom: 20 }}>
                    <View style={{ width: 60, height: 60, borderRadius: 30, backgroundColor: colors.errorSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
                      <Ionicons name="alert-circle" size={32} color={colors.error} />
                    </View>
                    <Text style={{ color: C.text, fontSize: 18, fontWeight: '800' }}>{t("autofix.watchSweep1.are.you.sure")}</Text>
                    <Text style={{ color: C.textMuted, fontSize: 13, textAlign: 'center', marginTop: 6 }}>{t("autofix.watchSweep1.this.action.will.cancel.your")}{currentPlan}{t("autofix.watchSweep1.subscription.at.the.end.of.the.billing.period")}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 10 }}>
                    <TouchableOpacity
                      onPress={() => setCancelStep('reason')}
                      style={{ flex: 1, backgroundColor: C.primary, paddingVertical: 12, borderRadius: 10, alignItems: 'center' }}
                    >
                      <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{t("common.goBack")}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      data-testid="confirm-cancel-btn" testID="confirm-cancel-btn"
                      onPress={confirmCancel}
                      disabled={cancelling}
                      style={{ flex: 1, backgroundColor: colors.error, paddingVertical: 12, borderRadius: 10, alignItems: 'center', opacity: cancelling ? 0.6 : 1 }}
                    >
                      {cancelling ? <ActivityIndicator color={colors.primaryText} size="small" /> : <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{t("autofix.watchSweep1.yes.cancel")}</Text>}
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {cancelStep === 'done' && (
                <View>
                  {cancelResult?.error ? (
                    <View style={{ alignItems: 'center' }}>
                      <Ionicons name="close-circle" size={48} color={colors.error} />
                      <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginTop: 12 }}>{t("autofix.watchSweep1.cancellation.failed")}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 13, textAlign: 'center', marginTop: 6 }}>{cancelResult.error}</Text>
                      <TouchableOpacity
                        onPress={() => setShowCancelModal(false)}
                        style={{ marginTop: 20, backgroundColor: C.primary, paddingHorizontal: 32, paddingVertical: 12, borderRadius: 10 }}
                      >
                        <Text style={{ color: colors.primaryText, fontWeight: '700' }}>{t("admin.themeDrift.bulk.close")}</Text>
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <View style={{ alignItems: 'center' }}>
                      <Ionicons name="checkmark-circle" size={48} color={colors.successText} />
                      <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginTop: 12 }} data-testid="cancel-success-title" testID="cancel-success-title">{t("autofix.watchSweep1.subscription.cancelled")}</Text>
                      <Text style={{ color: C.textMuted, fontSize: 13, textAlign: 'center', marginTop: 6 }}>{t("autofix.watchSweep1.your.access.continues.until")}{' '}
                        <Text style={{ color: C.text, fontWeight: '700' }}>
                          {cancelResult?.subscription_end_date ? new Date(cancelResult.subscription_end_date).toLocaleDateString() : 'end of billing period'}
                        </Text>
                      </Text>
                      {cancelResult?.ticket_id && (
                        <View style={{ backgroundColor: C.bgSoft, padding: 10, borderRadius: 8, marginTop: 12 }}>
                          <Text style={{ color: C.textMuted, fontSize: 11 }}>{t("autofix.watchSweep1.support.ticket")}<Text style={{ color: C.text, fontWeight: '700' }}>{cancelResult.ticket_id}</Text></Text>
                        </View>
                      )}
                      <Text style={{ color: C.textMuted, fontSize: 12, textAlign: 'center', marginTop: 12 }}>{t("autofix.watchSweep1.changed.your.mind.you.can.reactivate.anytime.before")}</Text>
                      <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
                        <TouchableOpacity
                          data-testid="reactivate-btn" testID="reactivate-btn"
                          onPress={handleReactivate}
                          disabled={cancelling}
                          style={{ flex: 1, backgroundColor: colors.success, paddingVertical: 12, borderRadius: 10, alignItems: 'center' }}
                        >
                          <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>{t("autofix.watchSweep1.reactivate")}</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          onPress={() => setShowCancelModal(false)}
                          style={{ flex: 1, backgroundColor: C.bgSoft, paddingVertical: 12, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: C.border }}
                        >
                          <Text style={{ color: C.textMuted, fontWeight: '700', fontSize: 14 }}>{t("admin.themeDrift.bulk.close")}</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  )}
                </View>
              )}
            </View>
          </View>
        </Modal>

        {/* ═══ PAYMENT METHOD PICKER MODAL ═══ */}
        {showPaymentPicker && selectedPlan && (
          <View style={StyleSheet.absoluteFillObject} data-testid="payment-method-picker" testID="payment-method-picker">
            <TouchableOpacity style={{ flex: 1, backgroundColor: colors.overlay }} onPress={() => setShowPaymentPicker(false)} activeOpacity={1} />
            <View style={{ position: 'absolute', bottom: 0, left: 0, right: 0, backgroundColor: C.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingHorizontal: 24, paddingTop: 16, paddingBottom: 10, maxHeight: '82%' }}>
              <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: C.border, alignSelf: 'center', marginBottom: 16 }} />
              <ScrollView showsVerticalScrollIndicator contentContainerStyle={{ paddingBottom: 10 }} data-testid="payment-picker-scroll" testID="payment-picker-scroll">
                <Text style={{ fontSize: 18, fontWeight: '800', color: C.text, marginBottom: 4 }} data-testid="payment-picker-title" testID="payment-picker-title">{t("autofix.watchSweep1.choose.payment.method")}</Text>
                <Text style={{ fontSize: 13, color: C.textMuted, marginBottom: 20 }}>
                  {selectedPlan.name}{t("autofix.watchSweep1.plan.2")}{billingPeriod === 'monthly' ? selectedPlan.monthly_price : selectedPlan.yearly_price}/{billingPeriod === 'monthly' ? 'mo' : 'yr'}
                </Text>

                {isAdmin ? (
                  <View
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: fedapaySyncTone.border, backgroundColor: fedapaySyncTone.bg, paddingVertical: 8, paddingHorizontal: 12, marginBottom: 14, alignSelf: 'flex-start' }}
                    data-testid="payment-picker-fedapay-sync-badge" testID="payment-picker-fedapay-sync-badge"
                  >
                    <Text style={{ color: fedapaySyncTone.text, fontSize: 11, fontWeight: '800' }} data-testid="payment-picker-fedapay-sync-text" testID="payment-picker-fedapay-sync-text">{t("autofix.watchSweep1.fedapay.fees.last.synced")}{fedapayLastSyncedLabel}
                    </Text>
                  </View>
                ) : null}

                <SecurePaymentAssurancePanel
                  provider="all"
                  context="modal"
                  panelTestId="payment-picker-secure-assurance-panel"
                />

                {/* Standard Payments */}
                <View style={{ marginBottom: 20 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Ionicons name="card" size={16} color={C.primary} />
                    <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{t("autofix.watchSweep1.stripe.international.payments")}</Text>
                  </View>
                  <PaymentMethodSelector
                    mode="navigate"
                    options={pickerStandardMethods}
                    availability={availableMethods}
                    onSelect={handlePaymentChoice}
                    colors={{
                      surface: C.bgSoft,
                      border: C.border,
                      text: C.text,
                      textMuted: C.textMuted,
                      primary: C.primary,
                      warningText: colors.warningText,
                      successText: colors.successText,
                    }}
                    containerTestId="payment-picker-standard-selector"
                  />
                </View>

                {/* FedaPay */}
                <View>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                    <Ionicons name="phone-portrait" size={16} color={colors.warningText} />
                    <Text style={{ fontSize: 14, fontWeight: '700', color: C.text }}>{t("autofix.watchSweep1.fedapay.west.africa")}</Text>
                  </View>
                  <PaymentMethodSelector
                    mode="navigate"
                    options={pickerMobileMethods}
                    availability={availableMethods}
                    onSelect={handlePaymentChoice}
                    colors={{
                      surface: C.bgSoft,
                      border: C.border,
                      text: C.text,
                      textMuted: C.textMuted,
                      primary: C.primary,
                      warningText: colors.warningText,
                      successText: colors.successText,
                    }}
                    containerTestId="payment-picker-mobile-selector"
                  />
                </View>

                <TouchableOpacity style={{ alignItems: 'center', paddingVertical: 14, marginTop: 16 }} onPress={() => setShowPaymentPicker(false)} data-testid="payment-picker-cancel" testID="payment-picker-cancel">
                  <Text style={{ color: C.textMuted, fontWeight: '600', fontSize: 14 }}>{t("admin.onboardingAB.actions.cancel")}</Text>
                </TouchableOpacity>
              </ScrollView>
            </View>
          </View>
        )}

        <Modal visible={showPaymentDetailsModal} transparent animationType="fade" onRequestClose={() => setShowPaymentDetailsModal(false)}>
          <TouchableOpacity
            style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 16 }}
            activeOpacity={1}
            onPress={() => setShowPaymentDetailsModal(false)}
            data-testid="plans-payment-details-modal-overlay"
            testID="plans-payment-details-modal-overlay"
          >
            <TouchableOpacity
              activeOpacity={1}
              onPress={() => {}}
              style={{ width: '100%', maxWidth: 960, maxHeight: '80%', backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 14 }}
              data-testid="plans-payment-details-modal"
              testID="plans-payment-details-modal"
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="plans-payment-details-modal-title" testID="plans-payment-details-modal-title">{tx('subscriptionPlans.paymentDetails.title', 'Payment Details & Fee Transparency')}</Text>
                <TouchableOpacity onPress={() => setShowPaymentDetailsModal(false)} data-testid="plans-payment-details-modal-close" testID="plans-payment-details-modal-close">
                  <Ionicons name="close" size={22} color={C.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 }} data-testid="plans-payment-details-gateway-filter" testID="plans-payment-details-gateway-filter">
                {([
                  { key: 'all', label: tx('subscriptionPlans.paymentDetails.filter.all', 'All') },
                  { key: 'stripe', label: 'Stripe' },
                  { key: 'paypal', label: 'PayPal' },
                  { key: 'fedapay', label: 'FedaPay' },
                  { key: 'apple_iap', label: 'Apple IAP' },
                  { key: 'google_iap', label: 'Google IAP' },
                ] as const).map((option) => {
                  const active = detailGatewayFilter === option.key;
                  return (
                    <TouchableOpacity
                      key={option.key}
                      onPress={() => {
                        setDetailGatewayFilter(option.key);
                        setSelectedPaymentDetailIndex(0);
                      }}
                      style={{
                        borderRadius: 999,
                        borderWidth: 1,
                        borderColor: active ? C.primary : C.border,
                        backgroundColor: active ? `${C.primary}20` : C.bgSoft,
                        paddingHorizontal: 10,
                        paddingVertical: 6,
                      }}
                      data-testid={`plans-payment-details-filter-${option.key}`}
                      testID={`plans-payment-details-filter-${option.key}`}
                    >
                      <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 10, fontWeight: '800' }}>{option.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.bgSoft, padding: 10, marginBottom: 10 }} data-testid="plans-payment-details-date-range" testID="plans-payment-details-date-range">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800', marginBottom: 8 }}>
                  {tx('subscriptionPlans.paymentDetails.dateRangeLabel', 'Date range (optional)')}
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  <TextInput
                    value={detailDateFromInput}
                    onChangeText={setDetailDateFromInput}
                    placeholder="YYYY-MM-DD"
                    placeholderTextColor={C.textMuted}
                    style={{
                      flex: 1,
                      minWidth: 150,
                      borderWidth: 1,
                      borderColor: C.border,
                      borderRadius: 8,
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                      color: C.text,
                      backgroundColor: C.card,
                      fontSize: 11,
                    }}
                    data-testid="plans-payment-details-date-from-input"
                    testID="plans-payment-details-date-from-input"
                  />
                  <TextInput
                    value={detailDateToInput}
                    onChangeText={setDetailDateToInput}
                    placeholder="YYYY-MM-DD"
                    placeholderTextColor={C.textMuted}
                    style={{
                      flex: 1,
                      minWidth: 150,
                      borderWidth: 1,
                      borderColor: C.border,
                      borderRadius: 8,
                      paddingHorizontal: 10,
                      paddingVertical: 8,
                      color: C.text,
                      backgroundColor: C.card,
                      fontSize: 11,
                    }}
                    data-testid="plans-payment-details-date-to-input"
                    testID="plans-payment-details-date-to-input"
                  />
                </View>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                  <TouchableOpacity
                    onPress={applyDetailDateRangeFilter}
                    style={{ borderRadius: 8, borderWidth: 1, borderColor: C.primary, backgroundColor: `${C.primary}20`, paddingHorizontal: 10, paddingVertical: 7 }}
                    data-testid="plans-payment-details-apply-date-filter"
                    testID="plans-payment-details-apply-date-filter"
                  >
                    <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>{tx('subscriptionPlans.paymentDetails.applyDateFilter', 'Apply')}</Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    onPress={clearDetailDateRangeFilter}
                    style={{ borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 7 }}
                    data-testid="plans-payment-details-clear-date-filter"
                    testID="plans-payment-details-clear-date-filter"
                  >
                    <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700' }}>{tx('subscriptionPlans.paymentDetails.clearDateFilter', 'Clear')}</Text>
                  </TouchableOpacity>
                </View>
              </View>

              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 }} data-testid="plans-payment-details-bulk-export-actions" testID="plans-payment-details-bulk-export-actions">
                <TouchableOpacity
                  disabled={bulkExportingDocType !== ''}
                  onPress={() => { void bulkExportFilteredRows('receipt'); }}
                  style={{
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: C.primary,
                    backgroundColor: bulkExportingDocType === 'receipt' ? `${C.primary}20` : C.card,
                    paddingHorizontal: 10,
                    paddingVertical: 7,
                    opacity: bulkExportingDocType !== '' && bulkExportingDocType !== 'receipt' ? 0.6 : 1,
                  }}
                  data-testid="plans-payment-details-bulk-export-receipts"
                  testID="plans-payment-details-bulk-export-receipts"
                >
                  <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>
                    {bulkExportingDocType === 'receipt'
                      ? tx('subscriptionPlans.paymentDetails.bulkExportLoading', 'Exporting...')
                      : tx('subscriptionPlans.paymentDetails.bulkExportReceipts', 'Export filtered receipts')}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  disabled={bulkExportingDocType !== ''}
                  onPress={() => { void bulkExportFilteredRows('invoice'); }}
                  style={{
                    borderRadius: 8,
                    borderWidth: 1,
                    borderColor: colors.warningText,
                    backgroundColor: bulkExportingDocType === 'invoice' ? `${colors.warningText}20` : C.card,
                    paddingHorizontal: 10,
                    paddingVertical: 7,
                    opacity: bulkExportingDocType !== '' && bulkExportingDocType !== 'invoice' ? 0.6 : 1,
                  }}
                  data-testid="plans-payment-details-bulk-export-invoices"
                  testID="plans-payment-details-bulk-export-invoices"
                >
                  <Text style={{ color: colors.warningText, fontSize: 10, fontWeight: '800' }}>
                    {bulkExportingDocType === 'invoice'
                      ? tx('subscriptionPlans.paymentDetails.bulkExportLoading', 'Exporting...')
                      : tx('subscriptionPlans.paymentDetails.bulkExportInvoices', 'Export filtered invoices')}
                  </Text>
                </TouchableOpacity>
              </View>

              {modalToast ? (
                <View
                  style={{
                    marginBottom: 10,
                    borderRadius: 10,
                    borderWidth: 1,
                    borderColor: modalToast.type === 'success' ? colors.successText : modalToast.type === 'error' ? colors.error : C.border,
                    backgroundColor: modalToast.type === 'success' ? colors.successSoft : modalToast.type === 'error' ? colors.errorSoft : C.bgSoft,
                    paddingHorizontal: 10,
                    paddingVertical: 8,
                  }}
                  data-testid="plans-payment-details-inline-toast"
                  testID="plans-payment-details-inline-toast"
                >
                  <Text style={{ color: modalToast.type === 'success' ? colors.successText : modalToast.type === 'error' ? colors.error : C.text, fontSize: 11, fontWeight: '700' }}>
                    {modalToast.message}
                  </Text>
                </View>
              ) : null}

              {selectedPaymentDetailRow ? (
                <View style={{ marginBottom: 10 }} data-testid="plans-payment-details-enterprise-fee-summary" testID="plans-payment-details-enterprise-fee-summary">
                  <EnterprisePaymentSummary
                    prefix="plans-payment-details-fee"
                    title={tx('payment.feeTransparency.title', 'Checkout Fee Transparency')}
                    colors={{
                      text: C.text,
                      textSecondary: C.textSec,
                      textMuted: C.textMuted,
                      border: C.border,
                      surface: C.card,
                      cardAlt: C.bgSoft,
                    }}
                    feeText={feeText}
                    loading={paymentDetailsLoading}
                    error={''}
                    rows={detailSummaryRows}
                    totalValue={formatDetailAmount(
                      selectedPaymentDetailRow?.total_amount
                      ?? selectedPaymentDetailRow?.amount_paid
                      ?? selectedPaymentDetailRow?.amount,
                      selectedPaymentDetailRow,
                    )}
                    feeNote={String(selectedPaymentDetailRow?.fee_visibility_note || tx('payment.feeTransparency.defaultNote', 'Tax Fee and Processing Fee are shown before payment.'))}
                    localization={detailLocalization}
                    policyText={`${tx('payment.feeTransparency.provider', 'Provider')}: ${selectedProviderLabel}`}
                    providerKey={selectedProviderKey as any}
                    providerLabel={selectedProviderLabel}
                    providerFormula={selectedProviderFormula}
                    providerMetaRows={detailProviderMetaRows}
                  />
                </View>
              ) : null}

              {paymentDetailsLoading ? (
                <View style={{ paddingVertical: 20, alignItems: 'center' }}>
                  <ActivityIndicator size="small" color={C.primary} />
                </View>
              ) : (
                <ScrollView showsVerticalScrollIndicator={false}>
                  {[...paymentDetailRows].slice(0, 8).map((row: any, idx: number) => (
                    <TouchableOpacity
                      key={`${row?.id || row?.payment_id || 'tx'}-${idx}`}
                      onPress={() => setSelectedPaymentDetailIndex(idx)}
                      style={{ borderWidth: 1.5, borderColor: idx === selectedPaymentDetailIndex ? C.primary : C.border, backgroundColor: idx % 2 === 0 ? C.bgSoft : C.card, borderRadius: 10, padding: 10, marginBottom: 8 }}
                      data-testid={`plans-payment-details-row-${idx}`}
                      testID={`plans-payment-details-row-${idx}`}
                    >
                      {(() => {
                        const txId = String(row?.transaction_id || row?.tx_id || row?.id || row?.payment_id || '').trim();
                        return (
                          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                            <Text style={{ color: C.textMuted, fontSize: 10, flex: 1 }} numberOfLines={1}>
                              TX: {txId || 'N/A'}
                            </Text>
                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                              <TouchableOpacity
                                onPress={() => handleCopyTransactionId(txId)}
                                style={{ paddingHorizontal: 9, paddingVertical: 5, borderRadius: 8, borderWidth: 1, borderColor: C.border, backgroundColor: copiedTransactionId === txId && txId ? colors.successSoft : C.card }}
                                data-testid={`plans-payment-details-copy-tx-${idx}`}
                                testID={`plans-payment-details-copy-tx-${idx}`}
                              >
                                <Text style={{ color: copiedTransactionId === txId && txId ? colors.successText : C.text, fontSize: 10, fontWeight: '700' }}>
                                  {copiedTransactionId === txId && txId ? tx('common.copied', 'Copied') : tx('subscriptionPlans.paymentDetails.copyId', 'Copy ID')}
                                </Text>
                              </TouchableOpacity>

                              {(() => {
                                const receiptId = resolveReceiptDownloadId(row);
                                const downloadKey = `${receiptId || 'row'}-${idx}`;
                                const loading = downloadingReceiptId === downloadKey;
                                const disabled = !receiptId || loading;
                                return (
                                  <TouchableOpacity
                                    disabled={disabled}
                                    onPress={() => {
                                      if (!disabled) {
                                        void downloadReceiptForRow(row, idx);
                                      }
                                    }}
                                    style={{
                                      paddingHorizontal: 9,
                                      paddingVertical: 5,
                                      borderRadius: 8,
                                      borderWidth: 1,
                                      borderColor: disabled ? C.border : C.primary,
                                      backgroundColor: loading ? `${C.primary}20` : (disabled ? C.bgSoft : C.card),
                                      opacity: disabled ? 0.7 : 1,
                                    }}
                                    data-testid={`plans-payment-details-download-receipt-${idx}`}
                                    testID={`plans-payment-details-download-receipt-${idx}`}
                                  >
                                    <Text style={{ color: disabled ? C.textMuted : C.primary, fontSize: 10, fontWeight: '800' }}>
                                      {loading
                                        ? tx('subscriptionPlans.paymentDetails.downloadingReceipt', 'Downloading...')
                                        : tx('subscriptionPlans.paymentDetails.downloadReceipt', 'Download receipt')}
                                    </Text>
                                  </TouchableOpacity>
                                );
                              })()}

                              {(() => {
                                const invoiceId = resolveReceiptDownloadId(row);
                                const downloadKey = `${invoiceId || 'row'}-${idx}`;
                                const loading = downloadingInvoiceId === downloadKey;
                                const disabled = !invoiceId || loading;
                                return (
                                  <TouchableOpacity
                                    disabled={disabled}
                                    onPress={() => {
                                      if (!disabled) {
                                        void downloadInvoiceForRow(row, idx);
                                      }
                                    }}
                                    style={{
                                      paddingHorizontal: 9,
                                      paddingVertical: 5,
                                      borderRadius: 8,
                                      borderWidth: 1,
                                      borderColor: disabled ? C.border : colors.warningText,
                                      backgroundColor: loading ? `${colors.warningText}20` : (disabled ? C.bgSoft : C.card),
                                      opacity: disabled ? 0.7 : 1,
                                    }}
                                    data-testid={`plans-payment-details-download-invoice-${idx}`}
                                    testID={`plans-payment-details-download-invoice-${idx}`}
                                  >
                                    <Text style={{ color: disabled ? C.textMuted : colors.warningText, fontSize: 10, fontWeight: '800' }}>
                                      {loading
                                        ? tx('subscriptionPlans.paymentDetails.downloadingInvoice', 'Downloading...')
                                        : tx('subscriptionPlans.paymentDetails.downloadInvoice', 'Download invoice')}
                                    </Text>
                                  </TouchableOpacity>
                                );
                              })()}
                            </View>
                          </View>
                        );
                      })()}
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{String(row?.gateway || row?.provider || 'Payment').toUpperCase()} · {String(row?.status || 'unknown').toUpperCase()}</Text>
                        {idx === selectedPaymentDetailIndex ? (
                          <View style={{ borderWidth: 1, borderColor: C.primary, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, backgroundColor: `${C.primary}15` }} data-testid={`plans-payment-details-selected-chip-${idx}`} testID={`plans-payment-details-selected-chip-${idx}`}>
                            <Text style={{ color: C.primary, fontSize: 9, fontWeight: '800' }}>{tx('subscriptionPlans.paymentDetails.selected', 'Selected')}</Text>
                          </View>
                        ) : null}
                      </View>
                      <Text style={{ color: C.textSec, fontSize: 11, marginTop: 3 }}>
                        {formatDetailAmount(row?.total_amount ?? row?.amount ?? row?.amount_paid ?? 0, row)}
                      </Text>
                      <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>{row?.created_at ? new Date(row.created_at).toLocaleString() : tx('subscriptionPlans.paymentDetails.timeUnavailable', 'Time unavailable')}</Text>
                    </TouchableOpacity>
                  ))}
                  {paymentDetailRows.length === 0 ? (
                    <Text style={{ color: C.textMuted, fontSize: 12, textAlign: 'center', paddingVertical: 20 }} data-testid="plans-payment-details-empty" testID="plans-payment-details-empty">
                      {tx('subscriptionPlans.paymentDetails.empty', 'No recent payment details found.')}
                    </Text>
                  ) : null}
                </ScrollView>
              )}

              <TouchableOpacity
                onPress={() => {
                  setShowPaymentDetailsModal(false);
                  router.push('/payment-history');
                }}
                style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingVertical: 11, alignItems: 'center' }}
                data-testid="plans-payment-details-open-full-history"
                testID="plans-payment-details-open-full-history"
              >
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('subscriptionPlans.paymentDetails.openFullHistory', 'Open full payment history')}</Text>
              </TouchableOpacity>
            </TouchableOpacity>
          </TouchableOpacity>
        </Modal>

      </SafeAreaView>

      {/* ═══ CURRENCY PICKER MODAL ═══ */}
      <Modal visible={showCurrencyPicker} transparent animationType="fade" onRequestClose={() => setShowCurrencyPicker(false)}>
        <TouchableOpacity activeOpacity={1} onPress={() => setShowCurrencyPicker(false)} style={{ flex: 1, backgroundColor: colors.overlay, justifyContent: 'center', alignItems: 'center' }}>
          <TouchableOpacity activeOpacity={1} style={{ backgroundColor: C.card, borderRadius: 20, width: isWide ? 400 : '90%', maxHeight: '70%', overflow: 'hidden', borderWidth: 1, borderColor: C.border }}>
            <View style={{ padding: 20, borderBottomWidth: 1, borderBottomColor: C.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <Text style={{ color: C.text, fontSize: 18, fontWeight: '700' }}>{t("autofix.precision12.select.currency")}</Text>
              <TouchableOpacity onPress={() => setShowCurrencyPicker(false)} data-testid="plans-currency-picker-close" testID="plans-currency-picker-close">
                <Ionicons name="close" size={24} color={C.textMuted} />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ maxHeight: 400 }} showsVerticalScrollIndicator={false}>
              <View style={{ paddingHorizontal: 8, paddingVertical: 8 }}>
                {sortedCurrencies.map((cur, idx) => {
                  const isSelected = cur.code === selectedCurrency;
                  const popularCount = POPULAR_CURRENCIES.filter(pc => currencies.some(c => c.code === pc)).length;
                  const isPopularEnd = idx === popularCount - 1;
                  return (
                    <View key={cur.code}>
                      <TouchableOpacity
                        onPress={() => {
                          setSelectedCurrency(cur.code);
                          setCurrencySymbol(cur.symbol);
                          setShowCurrencyPicker(false);
                          // Save preference to profile
                          api.put('/auth/profile', { currency_preference: cur.code }).then(() => refreshUser()).catch(() => {});
                        }}
                        style={{
                          flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 16,
                          borderRadius: 12, backgroundColor: isSelected ? (globalThis as any).__alphaColor(C.primary, '12') : 'transparent', marginBottom: 2,
                        }}
                        data-testid={`plans-currency-${cur.code}`} testID={`plans-currency-${cur.code}`}
                      >
                        <Text style={{ color: isSelected ? C.primary : C.text, fontSize: 15, fontWeight: isSelected ? '700' : '500', flex: 1 }}>
                          {cur.symbol}  {cur.name}
                        </Text>
                        <Text style={{ color: isSelected ? C.primary : C.textMuted, fontSize: 13, fontWeight: '600' }}>{cur.code}</Text>
                        {isSelected && <Ionicons name="checkmark-circle" size={18} color={C.primary} style={{ marginLeft: 8 }} />}
                      </TouchableOpacity>
                      {isPopularEnd && <View style={{ height: 1, backgroundColor: C.border, marginVertical: 6, marginHorizontal: 16 }} />}
                    </View>
                  );
                })}
              </View>
            </ScrollView>
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
    </AppShell>
  );
}
