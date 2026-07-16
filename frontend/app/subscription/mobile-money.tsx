import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Image, Platform, SafeAreaView, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import AppShell from '../../src/components/AppShell';
import CountryFlag from '../../src/components/CountryFlag';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import { useAccessControl } from '../../src/context/AccessControlContext';
import api from '../../src/services/api';
import { SecurePaymentAssurancePanel } from '../../src/components/payment/SecurePaymentAssurancePanel';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { normalizeReturnTarget } from '../../src/utils/subscriptionReturnTarget';
import { stashSubscriptionReturnToast } from '../../src/utils/subscriptionReturnToast';
import { SubscriptionSuccessPanel } from '../../src/components/payment/SubscriptionSuccessPanel';
import { SubscriptionUnlockedDestinationSummary } from '../../src/components/payment/SubscriptionUnlockedDestinationSummary';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

const COUNTRY_DIAL_CODES: Record<string, string> = {
  BJ: '+22901',
  TG: '+228',
  SN: '+221',
  CI: '+225',
  NE: '+227',
};

const COUNTRY_NAME_FALLBACKS: Record<string, string> = {
  BJ: 'Benin',
  TG: 'Togo',
  SN: 'Senegal',
  CI: "Côte d'Ivoire",
  NE: 'Niger',
};

const CARD_BRAND_LOGOS: Record<string, string> = {
  VISA: 'https://logo.clearbit.com/visa.com',
  MASTERCARD: 'https://logo.clearbit.com/mastercard.com',
};

const CARD_BRAND_FLAGS: Record<string, string> = {
  VISA: '🔷',
  MASTERCARD: '🔴🟡',
};

const FEDAPAY_PENDING_RESUME_URL_KEY = 'fedapay_pending_resume_url';
const FEDAPAY_PENDING_RESUME_EXPIRY_KEY = 'fedapay_pending_resume_expiry_at';
const FEDAPAY_PENDING_RESUME_TTL_MS = 30 * 60 * 1000;

const toCountryFlag = (code: string) => {
  const normalized = String(code || '').trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(normalized)) return '🌍';
  return String.fromCodePoint(...Array.from(normalized).map((char) => 127397 + char.charCodeAt(0)));
};

const toCountryFlagUrl = (code: string) => {
  const normalized = String(code || '').trim().toLowerCase();
  if (!/^[a-z]{2}$/.test(normalized)) return '';
  return `https://flagcdn.com/w40/${normalized}.png`;
};

const normalizeProviderKey = (value: string) => String(value || '')
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '-')
  .replace(/^-+|-+$/g, '');

const formatProviderLabel = (value: string) => {
  const cleaned = String(value || '').replace(/[_-]+/g, ' ').trim();
  if (!cleaned) return 'Provider';
  return cleaned.split(' ').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
};

const normalizePhoneForMatch = (value: string) => String(value || '').replace(/[\s()-]/g, '');

const formatDialCodeDisplay = (countryCode: string, dialCode: string) => {
  if (String(countryCode || '').toUpperCase() === 'BJ') return '+229 01';
  return String(dialCode || '');
};

const phonePlaceholderByCountry = (countryCode: string, dialCode: string) => {
  if (String(countryCode || '').toUpperCase() === 'BJ') return 'e.g. +229 01 97000000';
  return `e.g. ${dialCode}97000000`;
};

type CountryFeeSchedule = {
  default_mobile_fee_pct?: number;
  mobile_money_fees?: Record<string, number>;
  card_fee_pct?: number;
};

type GatewayOption = {
  id: string;
  label: string;
  status: string;
  mode: string;
  message: string;
  checked_at?: string;
  countries: string[];
  country_fee_schedule: Record<string, CountryFeeSchedule>;
  policy_source?: string;
  policy_updated_at?: string;
  supported_cards: string[];
};

type CountryRow = {
  code: string;
  name: string;
  flag: string;
  flagUrl: string;
  phoneCode: string;
  defaultFeePct: number;
  operators: Array<{ raw: string; key: string; label: string; feePct: number }>;
};

type CardMethodOption = {
  key: string;
  label: string;
  providerValue: string;
  logoUrl: string;
  flag: string;
  feePct: number;
};

type SavedCard = {
  card_id: string;
  card_type: string;
  last_four: string;
  expiry_month: number;
  expiry_year: number;
  is_default?: boolean;
};

export default function SubscriptionMobileMoneyPage() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const { colors: C } = useTheme();
  const { isAuthenticated, user, refreshUser } = useAuth();
  const { refresh: refreshAccessControl } = useAccessControl();
  const { t } = useTranslation();

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const planId = String(params.planId || 'basic');
  const planName = String(params.planName || planId || 'Plan');
  const billingPeriod = String(params.billingPeriod || 'monthly');
  const requestedCurrency = String(params.currency || 'xof').toUpperCase();
  const providerParam = String(params.provider || 'fedapay').toLowerCase();
  const returnTo = useMemo(() => normalizeReturnTarget(String(params.return_to || '/dashboard')), [params.return_to]);
  const currency = providerParam === 'fedapay'
    ? (requestedCurrency === 'XAF' ? 'XAF' : 'XOF')
    : requestedCurrency;

  const [phoneNumber, setPhoneNumber] = useState('');
  const [gateway, setGateway] = useState('fedapay');
  const [mobileProvider, setMobileProvider] = useState('');
  const [checkoutRail, setCheckoutRail] = useState<'mobile_money' | 'card'>('mobile_money');
  const [selectedCardMethodKey, setSelectedCardMethodKey] = useState('');
  const [selectedCountry, setSelectedCountry] = useState('BJ');
  const [gatewayOptions, setGatewayOptions] = useState<GatewayOption[]>([]);
  const [loadingGateways, setLoadingGateways] = useState(true);
  const [gatewayIssue, setGatewayIssue] = useState('');
  const [gatewayCheckedAt, setGatewayCheckedAt] = useState('');
  const [countryNameMap, setCountryNameMap] = useState<Record<string, string>>({});
  const [savedCards, setSavedCards] = useState<SavedCard[]>([]);
  const [selectedCardId, setSelectedCardId] = useState('');
  const [loadingSavedCards, setLoadingSavedCards] = useState(true);
  const [savedCardsIssue, setSavedCardsIssue] = useState('');
  const [pendingResumeUrl, setPendingResumeUrl] = useState('');
  const [pendingResumeMeta, setPendingResumeMeta] = useState('');
  const [pendingResumeExpiryAt, setPendingResumeExpiryAt] = useState<number | null>(null);
  const [resumeNowTs, setResumeNowTs] = useState<number>(Date.now());
  const [processing, setProcessing] = useState(false);
  const [showSuccessPanel, setShowSuccessPanel] = useState(false);

  const viewerIsAdmin = useMemo(() => hasAdminConsoleVisibility(user as any), [user]);

  const selectedGateway = useMemo(
    () => gatewayOptions.find((option) => option.id === gateway) || gatewayOptions[0] || null,
    [gateway, gatewayOptions],
  );

  const selectedGatewayStatus = String(selectedGateway?.status || 'unknown').toLowerCase();
  const selectedGatewayMode = String(selectedGateway?.mode || 'unknown').toUpperCase();
  const gatewayReadyForCheckout = selectedGatewayStatus !== 'inactive';

  const countryRows = useMemo<CountryRow[]>(() => {
    if (!selectedGateway) return [];
    const schedule = selectedGateway.country_fee_schedule || {};
    const countryCodes = selectedGateway.countries?.length
      ? selectedGateway.countries
      : Object.keys(schedule);

    return countryCodes.map((countryCodeRaw) => {
      const code = String(countryCodeRaw || '').toUpperCase();
      const countrySchedule = schedule[code] || {};
      const mobileFees = countrySchedule.mobile_money_fees || {};
      const operators = Object.entries(mobileFees).map(([rawName, feeRaw]) => {
        const feePct = Number(feeRaw || 0);
        return {
          raw: String(rawName),
          key: normalizeProviderKey(rawName),
          label: formatProviderLabel(String(rawName)),
          feePct: Number.isFinite(feePct) ? feePct : 0,
        };
      }).sort((a, b) => a.label.localeCompare(b.label));

      return {
        code,
        name: countryNameMap[code] || COUNTRY_NAME_FALLBACKS[code] || code,
        flag: toCountryFlag(code),
        flagUrl: toCountryFlagUrl(code),
        phoneCode: COUNTRY_DIAL_CODES[code] || '',
        defaultFeePct: Number(countrySchedule.default_mobile_fee_pct || 0),
        operators,
      };
    });
  }, [countryNameMap, selectedGateway]);

  const selectedCountryRow = useMemo(
    () => countryRows.find((row) => row.code === selectedCountry) || countryRows[0] || null,
    [countryRows, selectedCountry],
  );

  const selectedOperator = useMemo(
    () => selectedCountryRow?.operators.find((entry) => entry.raw.toLowerCase() === mobileProvider.toLowerCase()) || null,
    [mobileProvider, selectedCountryRow],
  );

  const supportedCardLabels = useMemo(
    () => (selectedGateway?.supported_cards || [])
      .map((card) => String(card || '').trim().toUpperCase())
      .filter(Boolean),
    [selectedGateway?.supported_cards],
  );

  const selectedCountryCardFeePct = useMemo(() => {
    const cardFee = selectedCountry
      ? selectedGateway?.country_fee_schedule?.[selectedCountry]?.card_fee_pct
      : undefined;
    const fallback = selectedGateway?.country_fee_schedule?.BJ?.card_fee_pct;
    const normalized = Number(cardFee ?? fallback ?? 0);
    return Number.isFinite(normalized) ? normalized : 0;
  }, [selectedCountry, selectedGateway]);

  const cardMethodOptions = useMemo<CardMethodOption[]>(
    () => supportedCardLabels.map((label) => {
      const normalized = String(label || '').toUpperCase();
      const key = normalized.toLowerCase().replace(/[^a-z0-9]+/g, '-');
      return {
        key,
        label: normalized,
        providerValue: `${normalized.toLowerCase()} card`,
        logoUrl: CARD_BRAND_LOGOS[normalized] || '',
        flag: CARD_BRAND_FLAGS[normalized] || '💳',
        feePct: selectedCountryCardFeePct,
      };
    }),
    [selectedCountryCardFeePct, supportedCardLabels],
  );

  const selectedCardMethod = useMemo(
    () => cardMethodOptions.find((option) => option.key === selectedCardMethodKey) || null,
    [cardMethodOptions, selectedCardMethodKey],
  );

  const paymentMode = checkoutRail;

  const selectedSavedCard = useMemo(
    () => savedCards.find((card) => card.card_id === selectedCardId) || null,
    [savedCards, selectedCardId],
  );

  const providerSupported = useMemo(() => {
    if (paymentMode === 'card') {
      return Boolean(selectedCardMethod);
    }
    const providerKey = String(mobileProvider || '').toLowerCase();
    if (!providerKey) return false;
    return Boolean(selectedCountryRow?.operators.some((entry) => entry.raw.toLowerCase() === providerKey));
  }, [mobileProvider, paymentMode, selectedCardMethod, selectedCountryRow]);

  const mobilePhonePrefixMismatch = useMemo(() => {
    if (paymentMode !== 'mobile_money') return '';
    const expectedPrefix = normalizePhoneForMatch(String(selectedCountryRow?.phoneCode || '').trim());
    const current = normalizePhoneForMatch(String(phoneNumber || '').trim());
    if (!expectedPrefix || !current || !current.startsWith('+')) return '';
    if (current.startsWith(expectedPrefix)) return '';
    return `Phone code must match selected country (${formatDialCodeDisplay(String(selectedCountryRow?.code || ''), expectedPrefix)}).`;
  }, [paymentMode, phoneNumber, selectedCountryRow?.phoneCode]);

  const gatewayTone = useMemo(() => {
    if (selectedGatewayStatus === 'active') {
      return {
        border: C.success,
        bg: `${C.success}14`,
        text: C.successText,
      };
    }
    if (selectedGatewayStatus === 'inactive') {
      return {
        border: C.error,
        bg: `${C.error}14`,
        text: C.error,
      };
    }
    return {
      border: C.warning,
      bg: `${C.warning}14`,
      text: C.warningText,
    };
  }, [C.error, C.success, C.successText, C.warning, C.warningText, selectedGatewayStatus]);

  const loadGateways = useCallback(async () => {
    setLoadingGateways(true);
    setGatewayIssue('');
    try {
      const [gatewaysResponse, gatewayConfigResponse, fedapayPolicyResponse] = await Promise.all([
        api.get('/subscriptions/mobile-money/gateways', { timeout: 12000 }),
        api.get(`/subscriptions/gateway-config?cb=${Date.now()}`, { timeout: 12000, silentLoading: true }).catch((error) => {
          handleAppRecoverableError({
            scope: 'subscription.mobile-money.gateway-config-fallback',
            error,
            message: 'Gateway config fallback activated.',
          
        notifyMode: 'silent',
      });
          return { data: null };
        }),
        api.get('/subscriptions/mobile-money/fedapay-policy', { timeout: 12000, silentLoading: true }).catch((error) => {
          handleAppRecoverableError({
            scope: 'subscription.mobile-money.fedapay-policy-fallback',
            error,
            message: 'FedaPay policy fallback activated.',
          
        notifyMode: 'silent',
      });
          return { data: null };
        }),
      ]);

      const rows = Array.isArray(gatewaysResponse?.data?.gateways) ? gatewaysResponse.data.gateways : [];
      const gatewayConfig = gatewayConfigResponse?.data || {};
      const policyCountries = fedapayPolicyResponse?.data?.countries || {};
      const names: Record<string, string> = {};
      Object.entries(policyCountries).forEach(([countryCode, config]: any) => {
        const key = String(countryCode || '').toUpperCase();
        const name = String(config?.name || '').trim();
        if (key && name) names[key] = name;
      });
      setCountryNameMap(names);

      const mapped: GatewayOption[] = rows.map((row: any) => {
        const statusRaw = String(row?.status || (row?.available === false ? 'inactive' : 'active')).toLowerCase();
        const modeRaw = String(row?.mode || gatewayConfig?.fedapay_mode || 'unknown').toLowerCase();
        const message = String(
          row?.message
          || (statusRaw === 'active'
            ? tx('mobileMoney.gateway.activeMessage', 'Gateway configured and ready for checkout.')
            : tx('mobileMoney.gateway.inactiveMessage', 'Gateway is currently unavailable. Contact support.')),
        );

        return {
          id: String(row?.id || 'fedapay').toLowerCase(),
          label: String(row?.label || row?.name || row?.id || 'FedaPay'),
          status: statusRaw,
          mode: modeRaw,
          message,
          checked_at: String(row?.checked_at || ''),
          countries: Array.isArray(row?.countries)
            ? row.countries.map((countryCode: any) => String(countryCode || '').toUpperCase()).filter(Boolean)
            : [],
          country_fee_schedule: typeof row?.country_fee_schedule === 'object' && row?.country_fee_schedule
            ? row.country_fee_schedule
            : {},
          policy_source: String(row?.policy_source || ''),
          policy_updated_at: String(row?.policy_updated_at || ''),
          supported_cards: Array.isArray(row?.supported_cards)
            ? row.supported_cards.map((card: any) => String(card || '')).filter(Boolean)
            : [],
        };
      });

      const fallbackGateway: GatewayOption = {
        id: 'fedapay',
        label: 'FedaPay',
        status: gatewayConfig?.fedapay_available ? 'active' : 'inactive',
        mode: String(gatewayConfig?.fedapay_mode || 'unknown').toLowerCase(),
        message: gatewayConfig?.fedapay_available
          ? tx('mobileMoney.gateway.activeMessage', 'Gateway configured and ready for checkout.')
          : tx('mobileMoney.gateway.inactiveMessage', 'Gateway is currently unavailable. Contact support.'),
        countries: Object.keys(names).length
          ? Object.keys(names)
          : ['BJ', 'TG', 'SN', 'CI', 'NE'],
        country_fee_schedule: {},
        policy_source: '',
        policy_updated_at: '',
        supported_cards: ['mastercard', 'visa'],
      };

      const normalized = mapped.length ? mapped : [fallbackGateway];
      const preferred = normalized.find((row) => row.status === 'active')?.id || normalized[0]?.id || 'fedapay';
      const preferredGateway = normalized.find((row) => row.id === preferred) || normalized[0] || fallbackGateway;
      const preferredCountries = preferredGateway?.countries?.length
        ? preferredGateway.countries
        : Object.keys(preferredGateway?.country_fee_schedule || {});

      setGatewayOptions(normalized);
      setGateway(preferred);
      setSelectedCountry((prev) => (preferredCountries.includes(prev) ? prev : (preferredCountries[0] || 'BJ')));
      setGatewayCheckedAt(new Date().toISOString());
    } catch (error) {
      handleAppRecoverableError({
        scope: 'subscription.mobile-money.load-gateways',
        error,
        message: tx('mobileMoney.gateway.degradedBanner', 'Live gateway status is temporarily unavailable. Showing fallback FedaPay option.'),
        setError: setGatewayIssue,
        onRetry: () => { void loadGateways(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      setGatewayIssue(tx('mobileMoney.gateway.degradedBanner', 'Live gateway status is temporarily unavailable. Showing fallback FedaPay option.'));
      setCountryNameMap((prev) => ({
        BJ: prev.BJ || COUNTRY_NAME_FALLBACKS.BJ,
        TG: prev.TG || COUNTRY_NAME_FALLBACKS.TG,
        SN: prev.SN || COUNTRY_NAME_FALLBACKS.SN,
        CI: prev.CI || COUNTRY_NAME_FALLBACKS.CI,
        NE: prev.NE || COUNTRY_NAME_FALLBACKS.NE,
      }));
      setGatewayOptions([
        {
          id: 'fedapay',
          label: 'FedaPay',
          status: 'degraded',
          mode: 'unknown',
          message: tx('mobileMoney.gateway.degradedMessage', 'Gateway status could not be verified right now. You can still continue checkout.'),
          countries: ['BJ', 'TG', 'SN', 'CI', 'NE'],
          country_fee_schedule: {},
          policy_source: '',
          policy_updated_at: '',
          supported_cards: ['mastercard', 'visa'],
        },
      ]);
      setGateway('fedapay');
      setSelectedCountry('BJ');
      setGatewayCheckedAt(new Date().toISOString());
    } finally {
      setLoadingGateways(false);
    }
  }, [tx]);

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace('/welcome?return_to=%2Fsubscription%2Fmobile-money&auth_reason=unauthenticated');
      return;
    }
    void loadGateways();
  }, [isAuthenticated, loadGateways, router]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    try {
      const persisted = String(window.localStorage.getItem(FEDAPAY_PENDING_RESUME_URL_KEY) || '').trim();
      const persistedExpiryRaw = String(window.localStorage.getItem(FEDAPAY_PENDING_RESUME_EXPIRY_KEY) || '').trim();
      const persistedExpiry = Number(persistedExpiryRaw || 0);
      if (persisted && Number.isFinite(persistedExpiry) && persistedExpiry > Date.now()) {
        setPendingResumeUrl(persisted);
        setPendingResumeMeta('Pending FedaPay checkout available to resume.');
        setPendingResumeExpiryAt(persistedExpiry);
      } else if (persisted) {
        window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_URL_KEY);
        window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_EXPIRY_KEY);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/mobile-money.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => {
    if (!pendingResumeUrl || !pendingResumeExpiryAt) return;
    const timer = setInterval(() => {
      setResumeNowTs(Date.now());
    }, 1000);
    return () => clearInterval(timer);
  }, [pendingResumeExpiryAt, pendingResumeUrl]);

  useEffect(() => {
    if (!pendingResumeUrl || !pendingResumeExpiryAt) return;
    if (pendingResumeExpiryAt <= resumeNowTs) {
      setPendingResumeUrl('');
      setPendingResumeMeta('');
      setPendingResumeExpiryAt(null);
      if (Platform.OS === 'web') {
        try {
          window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_URL_KEY);
          window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_EXPIRY_KEY);
        } catch (error) { handleAppRecoverableError({ scope: 'subscription/mobile-money.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      }
    }
  }, [pendingResumeExpiryAt, pendingResumeUrl, resumeNowTs]);

  const resumeCountdownLabel = useMemo(() => {
    if (!pendingResumeExpiryAt) return '';
    const remaining = Math.max(0, pendingResumeExpiryAt - resumeNowTs);
    const totalSeconds = Math.floor(remaining / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }, [pendingResumeExpiryAt, resumeNowTs]);

  const clearPendingResume = useCallback(() => {
    setPendingResumeUrl('');
    setPendingResumeMeta('');
    setPendingResumeExpiryAt(null);
    if (Platform.OS === 'web') {
      try {
        window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_URL_KEY);
        window.localStorage.removeItem(FEDAPAY_PENDING_RESUME_EXPIRY_KEY);
      } catch (error) { handleAppRecoverableError({ scope: 'subscription/mobile-money.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, []);

  const resumePendingPayment = useCallback(() => {
    if (!pendingResumeUrl) return;
    if (Platform.OS === 'web') {
      window.location.href = pendingResumeUrl;
      return;
    }
    Alert.alert('Resume payment', 'Open this checkout URL on web to continue pending FedaPay payment.');
  }, [pendingResumeUrl]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let mounted = true;
    const requestedCardId = String(params.savedCardId || '').trim();

    const loadSavedCards = async () => {
      setLoadingSavedCards(true);
      setSavedCardsIssue('');
      try {
        const { data } = await api.get('/payments/cards/checkout-ready', { timeout: 12000, silentLoading: true });
        if (!mounted) return;
        const cards: SavedCard[] = Array.isArray(data?.cards) ? data.cards : [];
        setSavedCards(cards);
        if (!cards.length) {
          setSelectedCardId('');
          return;
        }
        const preferred = requestedCardId
          ? cards.find((card) => card.card_id === requestedCardId)?.card_id
          : undefined;
        const defaultCardId = preferred || data?.default_card?.card_id || cards.find((card) => card.is_default)?.card_id || cards[0]?.card_id;
        setSelectedCardId(String(defaultCardId || ''));
      } catch (error) {
        handleAppRecoverableError({
          scope: 'subscription.mobile-money.load-saved-cards',
          error,
          message: 'Unable to load saved cards right now.',
          setError: setSavedCardsIssue,
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        if (!mounted) return;
        setSavedCards([]);
        setSelectedCardId('');
        setSavedCardsIssue('Unable to load saved cards right now.');
      } finally {
        if (mounted) setLoadingSavedCards(false);
      }
    };

    void loadSavedCards();
    return () => {
      mounted = false;
    };
  }, [isAuthenticated, params.savedCardId]);

  useEffect(() => {
    if (!selectedCountryRow) return;
    setMobileProvider((prev) => {
      const normalized = String(prev || '').toLowerCase();
      const available = selectedCountryRow.operators.some((entry) => entry.raw.toLowerCase() === normalized);
      if (available) return prev;
      return selectedCountryRow.operators[0]?.raw || '';
    });
    setPhoneNumber((prev) => {
      const current = normalizePhoneForMatch(String(prev || '').trim());
      const nextPrefix = String(selectedCountryRow.phoneCode || '').trim();
      if (!current) return nextPrefix;
      if (!current.startsWith('+')) return current;
      const knownPrefixes = Object.values(COUNTRY_DIAL_CODES).sort((a, b) => b.length - a.length);
      const matchedPrefix = knownPrefixes.find((prefix) => current.startsWith(prefix));
      if (!matchedPrefix || matchedPrefix === nextPrefix) return current;
      const rest = current.slice(matchedPrefix.length).replace(/^0+/, '');
      return `${nextPrefix}${rest}`;
    });
  }, [selectedCountryRow]);

  useEffect(() => {
    if (paymentMode !== 'card') return;
    if (!cardMethodOptions.length) {
      setSelectedCardMethodKey('');
      return;
    }
    setSelectedCardMethodKey((prev) => (cardMethodOptions.some((option) => option.key === prev)
      ? prev
      : cardMethodOptions[0].key));
  }, [cardMethodOptions, paymentMode]);

  const phoneValid = useMemo(() => {
    if (paymentMode === 'card') return true;
    const digits = phoneNumber.replace(/\D/g, '');
    return digits.length >= 8;
  }, [paymentMode, phoneNumber]);

  const submitDisableReason = useMemo(() => {
    if (!gatewayReadyForCheckout) return selectedGateway?.message || 'Gateway unavailable. Please contact support.';
    if (paymentMode === 'mobile_money' && !selectedCountryRow) return 'No active FedaPay country is available right now.';
    if (!providerSupported) return paymentMode === 'card'
      ? 'Select a valid card payment method.'
      : 'Select a valid FedaPay payment method for the selected country.';
    if (paymentMode === 'card' && !selectedCardId) return 'Select a saved card or add one to continue card checkout.';
    if (paymentMode === 'mobile_money' && mobilePhonePrefixMismatch) return mobilePhonePrefixMismatch;
    if (!phoneValid) return 'Please provide a valid mobile money phone number.';
    return '';
  }, [gatewayReadyForCheckout, mobilePhonePrefixMismatch, paymentMode, phoneValid, providerSupported, selectedCardId, selectedCountryRow, selectedGateway?.message]);

  const submit = async () => {
    if (!gatewayReadyForCheckout) {
      Alert.alert('Gateway unavailable', selectedGateway?.message || 'This gateway is currently unavailable.');
      return;
    }
    if (paymentMode === 'mobile_money' && !selectedCountryRow) {
      Alert.alert('Country unavailable', 'No supported country is available for this gateway.');
      return;
    }
    if (!providerSupported) {
      Alert.alert(
        'Payment method required',
        paymentMode === 'card'
          ? 'Select VISA or MASTERCARD to continue card checkout.'
          : 'Select a mobile provider supported for the selected country.',
      );
      return;
    }
    if (paymentMode === 'card' && !selectedCardId) {
      Alert.alert(
        'Saved card required',
        'Select a saved card to continue, or add one now from payment cards settings.',
        [
          { text: 'Manage Cards', onPress: () => router.push('/settings/payment-cards') },
          { text: 'Cancel', style: 'cancel' },
        ]
      );
      return;
    }
    if (paymentMode === 'mobile_money' && mobilePhonePrefixMismatch) {
      Alert.alert('Phone code mismatch', mobilePhonePrefixMismatch);
      return;
    }
    if (!phoneValid) {
      Alert.alert('Invalid phone number', 'Please provide a valid mobile money phone number.');
      return;
    }
    setProcessing(true);
    try {
      if (paymentMode === 'card') {
        const payload = {
          plan_id: planId,
          billing_period: billingPeriod,
          payment_method: 'card',
          saved_card_id: selectedCardId || undefined,
          currency,
        };
        const { data } = await api.post('/subscriptions/initiate-checkout', payload, { timeout: 25000 });
        const checkoutUrl = String(data?.checkout_url || data?.payment_url || '');
        if (checkoutUrl && Platform.OS === 'web') {
          window.location.href = checkoutUrl;
          return;
        }
        Alert.alert('Card checkout ready', String(data?.message || 'Continue card checkout to complete payment.'));
        return;
      }

      const phoneRaw = normalizePhoneForMatch(String(phoneNumber || '').trim());
      const prefix = selectedCountryRow.phoneCode;
      const normalizedPhone = phoneRaw.startsWith('+')
        ? phoneRaw
        : prefix
          ? `${prefix}${phoneRaw.replace(/^0+/, '')}`
          : phoneRaw;
      const payload = {
        plan_id: planId,
        billing_period: billingPeriod,
        gateway,
        phone_number: normalizedPhone,
        mobile_provider: mobileProvider,
        currency,
      };
      const { data } = await api.post('/subscriptions/mobile-money/pay', payload, { timeout: 25000 });
      const paymentUrl = String(data?.payment_url || '');
      const isDedupedPending = Boolean(data?.deduped) && String(data?.status || '').toLowerCase() === 'pending';
      if (isDedupedPending && paymentUrl) {
        const expiresAt = Date.now() + FEDAPAY_PENDING_RESUME_TTL_MS;
        setPendingResumeUrl(paymentUrl);
        setPendingResumeMeta(
          `Pending transaction reused (${String(data?.transaction_id || data?.payment_id || data?.ticket_id || 'existing')}).`,
        );
        setPendingResumeExpiryAt(expiresAt);
        if (Platform.OS === 'web') {
          try {
            window.localStorage.setItem(FEDAPAY_PENDING_RESUME_URL_KEY, paymentUrl);
            window.localStorage.setItem(FEDAPAY_PENDING_RESUME_EXPIRY_KEY, String(expiresAt));
          } catch (error) { handleAppRecoverableError({ scope: 'subscription/mobile-money.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        }
        Alert.alert(
          'Pending payment found',
          'A pending FedaPay checkout already exists. Resume now or later.',
          [
            { text: 'Later', style: 'cancel' },
            {
              text: 'Resume now',
              onPress: () => {
                if (Platform.OS === 'web') {
                  window.location.href = paymentUrl;
                }
              },
            },
          ],
        );
        return;
      }
      if (paymentUrl && Platform.OS === 'web') {
        window.location.href = paymentUrl;
        return;
      }
      if (String(data?.status || '').toLowerCase() === 'completed') {
        await refreshUser();
        await refreshAccessControl();
        setShowSuccessPanel(true);
        return;
      }
      Alert.alert('Payment initiated', String(data?.message || 'Continue your checkout to complete payment.'));
    } catch (e: any) {
      handleAppRecoverableError({
        scope: 'subscription.mobile-money.submit-payment',
        error: e,
        message: String(e?.response?.data?.detail || e?.message || 'Unable to initiate mobile money payment.'),
        onRetry: () => { void handleSubmitPayment(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
      Alert.alert('Payment failed', String(e?.response?.data?.detail || e?.message || 'Unable to initiate mobile money payment.'));
    } finally {
      setProcessing(false);
    }
  };

  return (
    <AppShell title="Mobile Money Checkout" subtitle="Complete your subscription with FedaPay mobile money">
      <SafeAreaView style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 28, paddingTop: 12 }}>
          {showSuccessPanel ? (
            <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }} data-testid="mobile-money-success-card" testID="mobile-money-success-card">
              <SubscriptionSuccessPanel
                amountText={null}
                badgeText={`Plan: ${planId.toUpperCase()} · ${billingPeriod} · ${currency}`}
                ctaLabel={tx('paymentResult.actions.goDashboard', 'Go to Dashboard')}
                colors={{
                  success: C.success,
                  successText: C.successText,
                  successSoft: C.successSoft,
                  text: C.text,
                  textMuted: C.textSec,
                  border: C.border,
                  bgSoft: C.bgSoft,
                  primaryText: C.primaryText,
                }}
                historyLabel={tx('paymentResult.actions.viewHistory', 'View Payment History')}
                onPressCta={() => { stashSubscriptionReturnToast(returnTo, planName); router.replace(returnTo as any); }}
                onPressHistory={() => router.replace('/payment-history')}
                preCtaContent={(
                  <SubscriptionUnlockedDestinationSummary
                    colors={{
                      success: C.success,
                      successText: C.successText,
                      text: C.text,
                      textMuted: C.textSec,
                      bgSoft: C.bgSoft,
                    }}
                    planName={planName}
                    providerKey="fedapay"
                    providerLabel={selectedGateway?.label || 'FedaPay'}
                    returnTarget={returnTo}
                    testIdPrefix="mobile-money-unlocked"
                    tx={tx}
                  />
                )}
                subtitle={tx('paymentResult.status.successMessage', 'Your subscription has been activated. Thank you for your payment!')}
                title={tx('paymentResult.status.successTitle', 'Payment Successful')}
              />
            </View>
          ) : (
          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 14 }} data-testid="mobile-money-checkout-card" testID="mobile-money-checkout-card">
            <Text style={{ color: C.text, fontSize: 16, fontWeight: '800' }} data-testid="mobile-money-checkout-title" testID="mobile-money-checkout-title">
              Subscribe with mobile money
            </Text>
            <Text style={{ color: C.textSec, fontSize: 12, marginTop: 6 }}>
              Plan: {planId.toUpperCase()} · {billingPeriod} · {currency}
            </Text>

            <View style={{ marginTop: 14 }} data-testid="mobile-money-secure-assurance-wrapper" testID="mobile-money-secure-assurance-wrapper">
              <SecurePaymentAssurancePanel
                provider="fedapay"
                context="checkout"
                panelTestId="mobile-money-secure-assurance-panel"
              />
            </View>

            {viewerIsAdmin && gatewayIssue ? (
              <View
                style={{ marginTop: 12, borderRadius: 10, borderWidth: 1, borderColor: C.warning, backgroundColor: `${C.warning}18`, paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="mobile-money-gateway-degraded-banner"
                testID="mobile-money-gateway-degraded-banner"
              >
                <Text style={{ color: C.warningText, fontSize: 11, fontWeight: '700' }}>
                  {gatewayIssue}
                </Text>
              </View>
            ) : null}

            <View style={{ marginTop: 14 }}>
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }}>Gateway</Text>
              {loadingGateways ? (
                <ActivityIndicator color={C.primary} data-testid="mobile-money-gateway-loading" testID="mobile-money-gateway-loading" />
              ) : (
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {gatewayOptions.map((option) => {
                    const active = gateway === option.id;
                    return (
                      <TouchableOpacity
                        key={option.id}
                        onPress={() => setGateway(option.id)}
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? C.primary : C.border, backgroundColor: active ? `${C.primary}15` : C.bgSoft, paddingHorizontal: 12, paddingVertical: 7 }}
                        data-testid={`mobile-money-gateway-${option.id}`}
                        testID={`mobile-money-gateway-${option.id}`}
                      >
                        <Text style={{ color: active ? C.primary : C.textSec, fontSize: 12, fontWeight: '700' }}>{option.label}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
            </View>

            {viewerIsAdmin ? (
              <View
                style={{
                  marginTop: 12,
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: gatewayTone.border,
                  backgroundColor: gatewayTone.bg,
                  paddingHorizontal: 12,
                  paddingVertical: 10,
                }}
                data-testid="mobile-money-gateway-status-card"
                testID="mobile-money-gateway-status-card"
              >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid="mobile-money-gateway-status-title" testID="mobile-money-gateway-status-title">
                  Gateway status
                </Text>
                <View style={{ borderRadius: 999, borderWidth: 1, borderColor: gatewayTone.text, backgroundColor: `${gatewayTone.text}1A`, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <Text style={{ color: gatewayTone.text, fontSize: 9, fontWeight: '800' }} data-testid="mobile-money-gateway-status-chip" testID="mobile-money-gateway-status-chip">
                    {selectedGatewayStatus.toUpperCase()} · {selectedGatewayMode}
                  </Text>
                </View>
              </View>
              <Text style={{ color: C.textSec, fontSize: 11, marginTop: 6 }} data-testid="mobile-money-gateway-status-message" testID="mobile-money-gateway-status-message">
                {selectedGateway?.message || tx('mobileMoney.gateway.defaultMessage', 'Gateway status available.')}
              </Text>
              {gatewayCheckedAt ? (
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-gateway-checked-at" testID="mobile-money-gateway-checked-at">
                  Last checked: {new Date(gatewayCheckedAt).toLocaleTimeString()}
                </Text>
              ) : null}
              {selectedGateway?.policy_source ? (
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-gateway-policy-source" testID="mobile-money-gateway-policy-source">
                  Policy source: {selectedGateway.policy_source}
                </Text>
              ) : null}
              {selectedGateway?.policy_updated_at ? (
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-gateway-policy-updated-at" testID="mobile-money-gateway-policy-updated-at">
                  Policy updated: {new Date(selectedGateway.policy_updated_at).toLocaleString()}
                </Text>
              ) : null}
              <View style={{ marginTop: 8 }} data-testid="mobile-money-gateway-card-methods" testID="mobile-money-gateway-card-methods">
                <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }} data-testid="mobile-money-gateway-card-methods-title" testID="mobile-money-gateway-card-methods-title">
                  FedaPay card methods
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                  {cardMethodOptions.map((card) => (
                    <View
                      key={`status-card-${card.key}`}
                      style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 4 }}
                      data-testid={`mobile-money-gateway-card-method-${card.key}`}
                      testID={`mobile-money-gateway-card-method-${card.key}`}
                    >
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                        {card.logoUrl ? (
                          <Image
                            source={{ uri: card.logoUrl }}
                            style={{ width: 16, height: 16, borderRadius: 8 }}
                            resizeMode="contain"
                          />
                        ) : (
                          <Text style={{ fontSize: 11 }}>{card.flag}</Text>
                        )}
                        <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>
                          {card.label}
                        </Text>
                      </View>
                    </View>
                  ))}
                  {!cardMethodOptions.length ? (
                    <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="mobile-money-gateway-card-method-empty" testID="mobile-money-gateway-card-method-empty">
                      No card methods published.
                    </Text>
                  ) : null}
                </View>
                {selectedCountryCardFeePct > 0 ? (
                  <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 6 }} data-testid="mobile-money-gateway-card-fee-note" testID="mobile-money-gateway-card-fee-note">
                    Card fee ({selectedCountry || 'default'}): {selectedCountryCardFeePct.toFixed(1)}%
                  </Text>
                ) : null}
              </View>
              </View>
            ) : null}

            <View
              style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 10 }}
              data-testid="mobile-money-rail-selector"
              testID="mobile-money-rail-selector"
            >
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>Checkout rail</Text>
              <View style={{ marginTop: 8, flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => setCheckoutRail('mobile_money')}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: paymentMode === 'mobile_money' ? C.primary : C.border, backgroundColor: paymentMode === 'mobile_money' ? `${C.primary}15` : C.bgSoft, paddingHorizontal: 12, paddingVertical: 7 }}
                  data-testid="mobile-money-rail-mobile-money-button"
                  testID="mobile-money-rail-mobile-money-button"
                >
                  <Text style={{ color: paymentMode === 'mobile_money' ? C.primary : C.textSec, fontSize: 11, fontWeight: '800' }}>Mobile Money</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => {
                    setCheckoutRail('card');
                    if (!selectedCardMethodKey && cardMethodOptions[0]?.key) setSelectedCardMethodKey(cardMethodOptions[0].key);
                  }}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: paymentMode === 'card' ? C.primary : C.border, backgroundColor: paymentMode === 'card' ? `${C.primary}15` : C.bgSoft, paddingHorizontal: 12, paddingVertical: 7 }}
                  data-testid="mobile-money-rail-card-button"
                  testID="mobile-money-rail-card-button"
                >
                  <Text style={{ color: paymentMode === 'card' ? C.primary : C.textSec, fontSize: 11, fontWeight: '800' }}>Card Payment</Text>
                </TouchableOpacity>
              </View>
            </View>

            {paymentMode === 'mobile_money' ? (
              <View
                style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }}
                data-testid="mobile-money-country-matrix-card"
                testID="mobile-money-country-matrix-card"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="mobile-money-country-matrix-title" testID="mobile-money-country-matrix-title">
                    FedaPay operating countries
                  </Text>
                  <TouchableOpacity
                    onPress={() => { void loadGateways(); }}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, paddingHorizontal: 10, paddingVertical: 5 }}
                    data-testid="mobile-money-country-refresh-button"
                    testID="mobile-money-country-refresh-button"
                  >
                    <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>Refresh</Text>
                  </TouchableOpacity>
                </View>
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-country-matrix-subtitle" testID="mobile-money-country-matrix-subtitle">
                  Select one country, then choose provider and phone.
                </Text>
                <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="mobile-money-country-card-methods" testID="mobile-money-country-card-methods">
                  {countryRows.map((country) => {
                    const active = selectedCountryRow?.code === country.code;
                    return (
                      <TouchableOpacity
                        key={country.code}
                        onPress={() => {
                          setCheckoutRail('mobile_money');
                          setSelectedCountry(country.code);
                        }}
                        style={{
                          minWidth: 176,
                          borderRadius: 10,
                          borderWidth: 1,
                          borderColor: active ? C.primary : C.border,
                          backgroundColor: active ? `${C.primary}14` : C.card,
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                        }}
                        data-testid={`mobile-money-country-${country.code.toLowerCase()}`}
                        testID={`mobile-money-country-${country.code.toLowerCase()}`}
                      >
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          {country.flagUrl ? (
                            <View
                              style={{ width: 30, height: 22, borderRadius: 4, borderWidth: 1, borderColor: C.border, overflow: 'hidden', backgroundColor: C.card }}
                              data-testid={`mobile-money-country-flag-image-wrap-${country.code.toLowerCase()}`}
                              testID={`mobile-money-country-flag-image-wrap-${country.code.toLowerCase()}`}
                            >
                              <Image
                                source={{ uri: country.flagUrl }}
                                style={{ width: '100%', height: '100%' }}
                                resizeMode="cover"
                                accessibilityLabel={`${country.name} flag`}
                              />
                            </View>
                          ) : (
                            <CountryFlag
                              code={country.code}
                              emoji={country.flag}
                              size={15}
                              data-testid={`mobile-money-country-flag-emoji-${country.code.toLowerCase()}`}
                            />
                          )}
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', flexShrink: 1 }} data-testid={`mobile-money-country-flag-name-${country.code.toLowerCase()}`} testID={`mobile-money-country-flag-name-${country.code.toLowerCase()}`}>
                            {country.name}
                          </Text>
                        </View>
                        {active ? (
                          <Text style={{ color: C.textSec, fontSize: 10, marginTop: 2 }} data-testid={`mobile-money-country-phone-code-${country.code.toLowerCase()}`} testID={`mobile-money-country-phone-code-${country.code.toLowerCase()}`}>
                            {country.code} · {formatDialCodeDisplay(country.code, country.phoneCode || 'N/A')}
                          </Text>
                        ) : null}
                        <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`mobile-money-country-operators-count-${country.code.toLowerCase()}`} testID={`mobile-money-country-operators-count-${country.code.toLowerCase()}`}>
                          {country.operators.length} providers · base fee {Number(country.defaultFeePct || 0).toFixed(1)}%
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                  {!countryRows.length ? (
                    <Text style={{ color: C.textMuted, fontSize: 11 }} data-testid="mobile-money-country-empty" testID="mobile-money-country-empty">
                      Country matrix is not available right now.
                    </Text>
                  ) : null}
                </View>
              </View>
            ) : (
              <View
                style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }}
                data-testid="mobile-money-card-methods-panel"
                testID="mobile-money-card-methods-panel"
              >
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="mobile-money-card-methods-title" testID="mobile-money-card-methods-title">
                  Card payment methods
                </Text>
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-card-methods-subtitle" testID="mobile-money-card-methods-subtitle">
                  Select one card method, then choose saved card payment below.
                </Text>
                <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {cardMethodOptions.map((card) => {
                    const active = selectedCardMethod?.key === card.key;
                    return (
                      <TouchableOpacity
                        key={`card-method-panel-${card.key}`}
                        onPress={() => {
                          setCheckoutRail('card');
                          setSelectedCardMethodKey(card.key);
                        }}
                        style={{
                          minWidth: 176,
                          borderRadius: 10,
                          borderWidth: 1,
                          borderColor: active ? C.primary : C.border,
                          backgroundColor: active ? `${C.primary}14` : C.card,
                          paddingHorizontal: 10,
                          paddingVertical: 8,
                        }}
                        data-testid={`mobile-money-country-card-method-${card.key}`}
                        testID={`mobile-money-country-card-method-${card.key}`}
                      >
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                          {card.logoUrl ? (
                            <View
                              style={{ width: 30, height: 22, borderRadius: 4, borderWidth: 1, borderColor: C.border, overflow: 'hidden', backgroundColor: C.card, alignItems: 'center', justifyContent: 'center' }}
                              data-testid={`mobile-money-country-card-method-logo-wrap-${card.key}`}
                              testID={`mobile-money-country-card-method-logo-wrap-${card.key}`}
                            >
                              <Image source={{ uri: card.logoUrl }} style={{ width: 26, height: 16 }} resizeMode="contain" />
                            </View>
                          ) : (
                            <Text style={{ fontSize: 16 }}>{card.flag}</Text>
                          )}
                          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid={`mobile-money-country-card-method-label-${card.key}`} testID={`mobile-money-country-card-method-label-${card.key}`}>
                            {card.label}
                          </Text>
                        </View>
                        <Text style={{ color: C.textSec, fontSize: 10, marginTop: 2 }}>
                          CARD PAYMENT
                        </Text>
                        <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }} data-testid={`mobile-money-country-card-method-fee-${card.key}`} testID={`mobile-money-country-card-method-fee-${card.key}`}>
                          base fee {Number(card.feePct || 0).toFixed(1)}%
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            )}

            <View
              style={{ marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.card, padding: 10 }}
              data-testid="mobile-money-saved-card-panel"
              testID="mobile-money-saved-card-panel"
            >
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="mobile-money-saved-card-title" testID="mobile-money-saved-card-title">
                  Saved Card Payment
                </Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <TouchableOpacity
                    onPress={() => router.push('/settings/payment-cards')}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid="mobile-money-saved-card-manage-button"
                    testID="mobile-money-saved-card-manage-button"
                  >
                    <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>Manage</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => router.push('/settings/payment-cards')}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.primary, backgroundColor: `${C.primary}12`, paddingHorizontal: 10, paddingVertical: 6 }}
                    data-testid="mobile-money-saved-card-add-button"
                    testID="mobile-money-saved-card-add-button"
                  >
                    <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800' }}>Add Card</Text>
                  </TouchableOpacity>
                </View>
              </View>
              <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 6 }} data-testid="mobile-money-saved-card-compatibility-note" testID="mobile-money-saved-card-compatibility-note">
                Checkout-ready card context is available across Stripe, PayPal, FedaPay, Apple IAP, and Google IAP.
              </Text>
              {loadingSavedCards ? (
                <ActivityIndicator color={C.primary} style={{ marginTop: 10 }} data-testid="mobile-money-saved-card-loading" testID="mobile-money-saved-card-loading" />
              ) : savedCards.length === 0 ? (
                <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 10 }} data-testid="mobile-money-saved-card-empty" testID="mobile-money-saved-card-empty">
                  No saved cards yet. Add one manually to enable instant card checkout from here.
                </Text>
              ) : (
                <View style={{ marginTop: 10, gap: 8 }} data-testid="mobile-money-saved-card-selector" testID="mobile-money-saved-card-selector">
                  {savedCards.map((card) => {
                    const active = selectedCardId === card.card_id;
                    return (
                      <TouchableOpacity
                        key={card.card_id}
                        onPress={() => setSelectedCardId(card.card_id)}
                        style={{ borderRadius: 10, borderWidth: 1.5, borderColor: active ? C.primary : C.border, backgroundColor: active ? `${C.primary}12` : C.bgSoft, paddingHorizontal: 10, paddingVertical: 9 }}
                        data-testid={`mobile-money-saved-card-option-${card.card_id}`}
                        testID={`mobile-money-saved-card-option-${card.card_id}`}
                      >
                        <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }}>
                          {String(card.card_type || 'card').toUpperCase()} •••• {String(card.last_four || '0000')}
                        </Text>
                        <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 2 }}>
                          Expires {String(card.expiry_month).padStart(2, '0')}/{String(card.expiry_year).slice(-2)} {card.is_default ? '· DEFAULT' : ''}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              )}
              {savedCardsIssue ? (
                <Text style={{ color: C.error, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-saved-card-error" testID="mobile-money-saved-card-error">
                  {savedCardsIssue}
                </Text>
              ) : null}
              {selectedSavedCard ? (
                <Text style={{ color: C.textSec, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-saved-card-selected-summary" testID="mobile-money-saved-card-selected-summary">
                  Selected saved card: {String(selectedSavedCard.card_type || 'card').toUpperCase()} •••• {selectedSavedCard.last_four}
                </Text>
              ) : null}
            </View>

            {paymentMode === 'mobile_money' ? (
              <View style={{ marginTop: 14 }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }} data-testid="mobile-money-provider-title" testID="mobile-money-provider-title">
                  Provider {selectedCountryRow ? `· ${selectedCountryRow.flag} ${selectedCountryRow.name}` : ''}
                </Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {(selectedCountryRow?.operators || []).map((provider) => {
                    const active = mobileProvider.toLowerCase() === provider.raw.toLowerCase();
                    return (
                      <TouchableOpacity
                        key={provider.key}
                        onPress={() => {
                          setCheckoutRail('mobile_money');
                          setMobileProvider(provider.raw);
                        }}
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: active ? C.primary : C.border, backgroundColor: active ? `${C.primary}15` : C.bgSoft, paddingHorizontal: 12, paddingVertical: 7 }}
                        data-testid={`mobile-money-provider-${provider.key}`}
                        testID={`mobile-money-provider-${provider.key}`}
                      >
                        <Text style={{ color: active ? C.primary : C.textSec, fontSize: 12, fontWeight: '700' }}>{provider.label} · {provider.feePct.toFixed(1)}%</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                {!selectedCountryRow?.operators.length ? (
                  <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-provider-empty-message" testID="mobile-money-provider-empty-message">
                    No mobile providers are configured for this country yet.
                  </Text>
                ) : null}
                {selectedOperator ? (
                  <Text style={{ color: C.textSec, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-provider-selected-summary" testID="mobile-money-provider-selected-summary">
                    Selected provider: {selectedOperator.label} · Fee {selectedOperator.feePct.toFixed(1)}%
                  </Text>
                ) : null}
              </View>
            ) : (
              <View style={{ marginTop: 14 }}>
                {selectedCardMethod ? (
                  <Text style={{ color: C.textSec, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-card-method-selected-summary" testID="mobile-money-card-method-selected-summary">
                    Selected card method: {selectedCardMethod.label} · Base fee {Number(selectedCardMethod.feePct || 0).toFixed(1)}% · Use saved card payment below.
                  </Text>
                ) : (
                  <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 8 }} data-testid="mobile-money-card-method-unselected" testID="mobile-money-card-method-unselected">
                    Select VISA or MASTERCARD to continue card checkout.
                  </Text>
                )}
              </View>
            )}

            {paymentMode === 'mobile_money' ? (
              <View style={{ marginTop: 14 }}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', marginBottom: 8 }}>Phone number</Text>
                {selectedCountryRow ? (
                  <Text style={{ color: C.textMuted, fontSize: 10, marginBottom: 6 }} data-testid="mobile-money-phone-country-hint" testID="mobile-money-phone-country-hint">
                    Country format: {selectedCountryRow.flag} {selectedCountryRow.name} ({formatDialCodeDisplay(selectedCountryRow.code, selectedCountryRow.phoneCode || 'N/A')})
                  </Text>
                ) : null}
                <TextInput
                  value={phoneNumber}
                  onChangeText={setPhoneNumber}
                  placeholder={phonePlaceholderByCountry(String(selectedCountryRow?.code || ''), String(selectedCountryRow?.phoneCode || '+229'))}
                  placeholderTextColor={C.textMuted}
                  keyboardType="phone-pad"
                  style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, color: C.text, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13 }}
                  data-testid="mobile-money-phone-input"
                  testID="mobile-money-phone-input"
                />
              </View>
            ) : (
              <View style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, padding: 10 }} data-testid="mobile-money-card-mode-info" testID="mobile-money-card-mode-info">
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>
                  Card mode active ({selectedCardMethod?.label || 'CARD'})
                </Text>
                <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 4 }}>
                  Select a preferred saved card above, or add a new card manually.
                </Text>
              </View>
            )}

            {pendingResumeUrl ? (
              <View
                style={{ marginTop: 14, borderRadius: 10, borderWidth: 1, borderColor: C.primary, backgroundColor: `${C.primary}12`, padding: 10 }}
                data-testid="mobile-money-resume-pending-cta-card"
                testID="mobile-money-resume-pending-cta-card"
              >
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '800' }} data-testid="mobile-money-resume-pending-title" testID="mobile-money-resume-pending-title">
                  Resume pending FedaPay payment
                </Text>
                {resumeCountdownLabel ? (
                  <Text style={{ color: C.warningText, fontSize: 10, marginTop: 4, fontWeight: '700' }} data-testid="mobile-money-resume-countdown" testID="mobile-money-resume-countdown">
                    Link expires soon: {resumeCountdownLabel}
                  </Text>
                ) : null}
                {pendingResumeMeta ? (
                  <Text style={{ color: C.textSec, fontSize: 10, marginTop: 4 }} data-testid="mobile-money-resume-pending-meta" testID="mobile-money-resume-pending-meta">
                    {pendingResumeMeta}
                  </Text>
                ) : null}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
                  <TouchableOpacity
                    onPress={resumePendingPayment}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.primary, backgroundColor: C.primary, paddingHorizontal: 12, paddingVertical: 7 }}
                    data-testid="mobile-money-resume-pending-button"
                    testID="mobile-money-resume-pending-button"
                  >
                    <Text style={{ color: C.primaryText, fontSize: 10, fontWeight: '800' }}>Resume</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={clearPendingResume}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 12, paddingVertical: 7 }}
                    data-testid="mobile-money-dismiss-pending-button"
                    testID="mobile-money-dismiss-pending-button"
                  >
                    <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '700' }}>Dismiss</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : null}

            <TouchableOpacity
              onPress={submit}
              disabled={processing || Boolean(submitDisableReason)}
              style={{ marginTop: 16, borderRadius: 12, backgroundColor: processing || Boolean(submitDisableReason) ? C.border : C.primary, paddingVertical: 12, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 }}
              data-testid="mobile-money-submit-button"
              testID="mobile-money-submit-button"
            >
              {processing ? <ActivityIndicator color={C.primaryText} /> : <Ionicons name={paymentMode === 'card' ? 'card-outline' : 'cash-outline'} size={16} color={C.primaryText} />}
              <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>
                {paymentMode === 'card' ? 'Continue to saved card payment' : 'Continue to mobile money checkout'}
              </Text>
            </TouchableOpacity>

            {submitDisableReason ? (
              <Text style={{ color: C.error, fontSize: 11, marginTop: 8 }} data-testid="mobile-money-submit-disabled-reason" testID="mobile-money-submit-disabled-reason">
                {submitDisableReason}
              </Text>
            ) : null}
          </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </AppShell>
  );
}

/* i18n-probe t('i18n.auto.probe') */
