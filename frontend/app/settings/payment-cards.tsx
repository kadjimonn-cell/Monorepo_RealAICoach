import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, TextInput, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../../src/components/AppShell';
import { useTheme } from '../../src/context/ThemeContext';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import { useAutoRefresh } from '../../src/hooks/useAutoRefresh';
import { PaymentHistorySkeleton } from '../../src/components/SkeletonLoaders';
import { loadStripe } from '@stripe/stripe-js';
import type { Stripe, StripeCardElement } from '@stripe/stripe-js';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';

/* ── Card brand config ── */
const BRANDS: Record<string, { bgTone: string; markerTone: string; label: string }> = {
  visa:       { bgTone: 'primary', markerTone: 'warning', label: 'VISA' },
  mastercard: { bgTone: 'surface', markerTone: 'error', label: 'Mastercard' },
  amex:       { bgTone: 'info', markerTone: 'text', label: 'American Express' },
  discover:   { bgTone: 'warning', markerTone: 'text', label: 'Discover' },
  other:      { bgTone: 'textSec', markerTone: 'textMuted', label: 'Card' },
};

function MetricTile({
  title,
  value,
  helper,
  icon,
  color,
  testId,
}: {
  title: string;
  value: string;
  helper: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  testId: string;
}) {
  return (
    <View
      style={{
        flex: 1,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: `${color}28`,
        backgroundColor: `${color}12`,
        padding: 12,
      }}
      data-testid={testId}
      testID={testId}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={icon} size={14} color={color} />
        <Text style={{ color: color, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 }}>
          {title}
        </Text>
      </View>
      <Text style={{ color: color, fontSize: 15, fontWeight: '800', marginTop: 4 }} numberOfLines={1}>{value}</Text>
      <Text style={{ color: color, fontSize: 10, marginTop: 2 }} numberOfLines={2}>{helper}</Text>
    </View>
  );
}

function formatGatewayLabel(raw: string) {
  const key = String(raw || '').toLowerCase();
  if (key === 'iap_apple' || key === 'apple_iap') return 'Apple IAP';
  if (key === 'iap_google' || key === 'google_iap') return 'Google IAP';
  if (key === 'fedapay') return 'FedaPay';
  if (key === 'paypal') return 'PayPal';
  if (key === 'stripe') return 'Stripe';
  return key.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ── Stripe Elements Card Input (PCI-compliant iframe) ── */
function StripeCardInput({
  colors,
  darkMode,
  onReady,
  onError,
}: {
  colors: any;
  darkMode: boolean;
  onReady: (element: StripeCardElement) => void;
  onError: (msg: string) => void;
}) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const stripeRef = useRef<Stripe | null>(null);
  const elementRef = useRef<StripeCardElement | null>(null);
  const [loading, setLoading] = useState(true);
  const [elementError, setElementError] = useState<string | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    let cancelled = false;

    (async () => {
      try {
        const configRes = await api.get('/payments/config');
        const publishableKey = configRes.data?.stripe_publishable_key;
        if (!publishableKey || cancelled) {
          if (!cancelled) onError('Payment processing unavailable.');
          return;
        }

        const stripe = await loadStripe(publishableKey);
        if (!stripe || cancelled) {
          if (!cancelled) onError('Failed to load payment processor.');
          return;
        }
        stripeRef.current = stripe;

        const elements = stripe.elements();
        const cardElement = elements.create('card', {
          style: {
            base: {
              fontSize: '15px',
              fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              color: colors.text,
              '::placeholder': { color: darkMode ? colors.textDim : colors.textMuted },
              iconColor: darkMode ? colors.textDim : colors.textMuted,
            },
            invalid: { color: colors.error, iconColor: colors.error },
          },
          hidePostalCode: true,
        });

        if (containerRef.current && !cancelled) {
          cardElement.mount(containerRef.current);
          elementRef.current = cardElement;

          cardElement.on('change', (event) => {
            setElementError(event.error?.message || null);
          });

          cardElement.on('ready', () => {
            if (!cancelled) {
              setLoading(false);
              onReady(cardElement);
            }
          });
        }
      } catch (err: any) {
        if (!cancelled) onError(err.message || 'Failed to initialize payment form.');
      }
    })();

    return () => {
      cancelled = true;
      if (elementRef.current) {
        try { elementRef.current.unmount(); } catch (error) { handleAppRecoverableError({ scope: 'settings/payment-cards.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
        elementRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [darkMode]);

  if (Platform.OS !== 'web') return null;

  return (
    <View>
      <View style={{ position: 'relative' }}>
        {loading && (
          <View style={{
            flexDirection: 'row', alignItems: 'center', gap: 8,
            padding: 14, borderRadius: 8,
            backgroundColor: darkMode ? colors.surface : colors.primaryText,
            borderWidth: 1, borderColor: darkMode ? colors.border : colors.surfaceHover,
          }}>
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ color: colors.textMuted, fontSize: 13 }}>{t("autofix.precision12.loading.secure.card.form")}</Text>
          </View>
        )}
        <div
          ref={containerRef}
          data-testid="stripe-card-element"
          style={{
            padding: '14px',
            borderRadius: '8px',
            backgroundColor: darkMode ? colors.surface : colors.primaryText,
            border: `1px solid ${elementError ? `${colors.error}15` : (darkMode ? colors.border : colors.surfaceHover)}`,
            minHeight: '44px',
            display: loading ? 'none' : 'block',
            transition: 'border-color 0.15s ease',
          }}
        />
      </View>
      {elementError && (
        <Text style={{ color: colors.error, fontSize: 11, marginTop: 4 }} data-testid="stripe-card-error" testID="stripe-card-error">
          {elementError}
        </Text>
      )}
    </View>
  );
}

/* ── Helpers (edit form only — no raw card data) ── */
function fmtExpiry(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 4);
  if (d.length >= 3) return `${d.slice(0, 2)}/${d.slice(2)}`;
  return d;
}

function isExpiryValid(exp: string): { valid: boolean; month: number; year: number } {
  const parts = exp.split('/');
  if (parts.length !== 2) return { valid: false, month: 0, year: 0 };
  const month = parseInt(parts[0], 10);
  const yearRaw = parseInt(parts[1], 10);
  const year = yearRaw < 100 ? 2000 + yearRaw : yearRaw;
  if (month < 1 || month > 12) return { valid: false, month, year };
  const now = new Date();
  const curMonth = now.getMonth() + 1;
  const curYear = now.getFullYear();
  if (year < curYear || (year === curYear && month < curMonth)) return { valid: false, month, year };
  return { valid: true, month, year };
}

/* ── Types ── */
interface CardData {
  card_id: string;
  card_type: string;
  masked_number: string;
  cardholder_name: string;
  expiry_month: number;
  expiry_year: number;
  is_default: boolean;
  last_four: string;
  status: string;
  valid_for_checkout?: boolean;
  validity_status?: 'valid' | 'expiring_soon' | 'expired';
  usable_gateways?: string[];
}

type FormField = 'cardholder_name' | 'expiry';

export default function PaymentCardsPage() {
  const { t } = useTranslation();
  t('i18n.route.settings.payment-cards.probe');
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { darkMode , colors} = useTheme();
  const { isAuthenticated } = useAuth();
  const { width } = useWindowDimensions();
  const isMobile = width < 760;
  const isDesktop = width >= 1180;
  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FormField, string>>>({});
  const [form, setForm] = useState({ cardholder_name: '', expiry: '' });

  /* Stripe Element refs */
  const stripeInstanceRef = useRef<Stripe | null>(null);
  const cardElementRef = useRef<StripeCardElement | null>(null);
  const [stripeReady, setStripeReady] = useState(false);
  const [stripeInitError, setStripeInitError] = useState<string | null>(null);

  const validCardsCount = useMemo(
    () => cards.filter((card) => card.valid_for_checkout !== false && card.validity_status !== 'expired').length,
    [cards],
  );
  const expiringCardsCount = useMemo(
    () => cards.filter((card) => card.validity_status === 'expiring_soon').length,
    [cards],
  );
  const defaultCard = useMemo(
    () => cards.find((card) => card.is_default) || null,
    [cards],
  );
  const observedGateways = useMemo(() => {
    const registry = new Set<string>();
    cards.forEach((card) => {
      (card.usable_gateways || []).forEach((gateway) => {
        const normalized = String(gateway || '').trim().toLowerCase();
        if (normalized) registry.add(normalized);
      });
    });
    return Array.from(registry);
  }, [cards]);

  const showToast = (type: 'success' | 'error', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 4000);
  };

  const loadCards = useCallback(async () => {
    try {
      setLoading(true);
      const res = await api.get('/payments/cards');
      setCards(res.data.cards || []);
    } catch {
      showToast('error', tx('paymentCards.toast.loadFailed', 'Failed to load cards'));
    } finally {
      setLoading(false);
    }
  }, [tx]);

  useEffect(() => { if (isAuthenticated) loadCards(); }, [isAuthenticated, loadCards]);
  useAutoRefresh(loadCards, { intervalMs: 30000 });

  /* Initialize Stripe when the publishable key loads */
  useEffect(() => {
    if (!showAdd || Platform.OS !== 'web') return;
    let cancelled = false;

    (async () => {
      try {
        const configRes = await api.get('/payments/config');
        const publishableKey = configRes.data?.stripe_publishable_key;
        if (!publishableKey || cancelled) return;
        const stripe = await loadStripe(publishableKey);
        if (stripe && !cancelled) {
          stripeInstanceRef.current = stripe;
        }
      } catch (error) { handleAppRecoverableError({ scope: 'settings/payment-cards.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    })();

    return () => { cancelled = true; };
  }, [showAdd]);

  const resetForm = () => {
    setForm({ cardholder_name: '', expiry: '' });
    setFieldErrors({});
    setStripeReady(false);
    setStripeInitError(null);
    cardElementRef.current = null;
  };

  const handleCardElementReady = useCallback((element: StripeCardElement) => {
    cardElementRef.current = element;
    setStripeReady(true);
  }, []);

  const handleStripeInitError = useCallback((msg: string) => {
    setStripeInitError(msg);
  }, []);

  /* ── Add Card ── */
  const handleAdd = async () => {
    const errors: Partial<Record<FormField, string>> = {};
    if (!form.cardholder_name.trim()) errors.cardholder_name = tx('paymentCards.validation.nameRequired', 'Name is required');
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    if (!stripeInstanceRef.current || !cardElementRef.current) {
      showToast('error', tx('paymentCards.toast.formNotReady', 'Payment form not ready. Please wait a moment and try again.'));
      return;
    }

    setSaving(true);
    try {
      const { token, error } = await stripeInstanceRef.current.createToken(
        cardElementRef.current,
        { name: form.cardholder_name.trim() }
      );

      if (error || !token) {
        showToast('error', error?.message || tx('paymentCards.toast.cardVerifyFailed', 'Card verification failed. Please check your details.'));
        setSaving(false);
        return;
      }

      await api.post('/payments/cards/add', {
        stripe_token: token.id,
        cardholder_name: form.cardholder_name.trim(),
      });

      showToast('success', tx('paymentCards.toast.addSuccess', 'Card verified and added successfully'));
      resetForm();
      setShowAdd(false);
      loadCards();
    } catch (e: any) {
      showToast('error', e.response?.data?.detail || e.message || tx('paymentCards.toast.addFailed', 'Failed to add card'));
    } finally {
      setSaving(false);
    }
  };

  /* ── Remove Card ── */
  const handleRemove = async (cardId: string) => {
    setActionLoading(cardId);
    try {
      await api.delete(`/payments/cards/${cardId}`);
      showToast('success', tx('paymentCards.toast.removeSuccess', 'Card removed successfully'));
      setRemovingId(null);
      loadCards();
    } catch (e: any) {
      showToast('error', e.response?.data?.detail || tx('paymentCards.toast.removeFailed', 'Failed to remove card'));
    } finally {
      setActionLoading(null);
    }
  };

  /* ── Set Default ── */
  const handleSetDefault = async (cardId: string) => {
    setActionLoading(cardId);
    try {
      await api.post('/payments/cards/set-default', { card_id: cardId });
      showToast('success', tx('paymentCards.toast.defaultUpdated', 'Default card updated'));
      loadCards();
    } catch (e: any) {
      showToast('error', e.response?.data?.detail || tx('paymentCards.toast.defaultUpdateFailed', 'Failed to update default'));
    } finally {
      setActionLoading(null);
    }
  };

  /* ── Update Card ── */
  const handleUpdate = async (cardId: string) => {
    const errors: Partial<Record<FormField, string>> = {};
    if (!form.cardholder_name.trim()) errors.cardholder_name = tx('paymentCards.validation.nameRequired', 'Name is required');
    if (form.expiry) {
      const exp = isExpiryValid(form.expiry);
      if (!exp.valid) errors.expiry = tx('paymentCards.validation.expiryInvalid', 'Invalid or expired date');
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setActionLoading(cardId);
    const payload: any = { card_id: cardId };
    if (form.cardholder_name.trim()) payload.cardholder_name = form.cardholder_name.trim();
    if (form.expiry) {
      const { month, year } = isExpiryValid(form.expiry);
      payload.expiry_month = month;
      payload.expiry_year = year;
    }
    try {
      await api.put('/payments/cards/update', payload);
      showToast('success', tx('paymentCards.toast.updateSuccess', 'Card updated successfully'));
      setEditingId(null);
      resetForm();
      loadCards();
    } catch (e: any) {
      showToast('error', e.response?.data?.detail || tx('paymentCards.toast.updateFailed', 'Failed to update card'));
    } finally {
      setActionLoading(null);
    }
  };

  const startEdit = (card: CardData) => {
    setEditingId(card.card_id);
    setRemovingId(null);
    setShowAdd(false);
    setForm({
      cardholder_name: card.cardholder_name,
      expiry: `${String(card.expiry_month).padStart(2, '0')}/${String(card.expiry_year).slice(-2)}`,
    });
    setFieldErrors({});
  };

  const cancelEdit = () => {
    setEditingId(null);
    resetForm();
  };

  /* ── Unauthenticated state ── */
  if (!isAuthenticated) {
    return (
      <AppShell>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg }}>
          <View style={{ width: 64, height: 64, borderRadius: 20, backgroundColor: `${colors.primary}15`, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
            <Ionicons name="lock-closed" size={28} color={colors.primary} />
          </View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700', marginBottom: 6 }}>{t("autofix.precision12.authentication.required")}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 13 }}>{t("autofix.precision12.sign.in.to.manage.payment.cards")}</Text>
        </View>
      </AppShell>
    );
  }

  const isWeb = Platform.OS === 'web';
  const mono = isWeb ? 'monospace' : undefined;

  return (
    <AppShell>
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.bg }}
        contentContainerStyle={{
          paddingHorizontal: isMobile ? 14 : 24,
          paddingTop: isMobile ? 14 : 20,
          paddingBottom: 100,
          maxWidth: 1240,
          width: '100%',
          alignSelf: 'center',
        }}
        data-testid="payment-cards-page" testID="payment-cards-page"
      >
        <View
          style={{
            borderRadius: 20,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.card,
            padding: isMobile ? 16 : 22,
            marginBottom: 16,
          }}
          data-testid="payment-cards-hero"
          testID="payment-cards-hero"
        >
          <View style={{ flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between', gap: 14 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <View style={{ width: 52, height: 52, borderRadius: 16, backgroundColor: `${colors.primary}12`, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: `${colors.primary}32` }}>
                <Ionicons name="wallet" size={24} color={colors.primary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: colors.text, fontSize: isMobile ? 28 : 34, fontWeight: '800', letterSpacing: -0.8 }} data-testid="payment-cards-title" testID="payment-cards-title">
                  {tx('paymentCards.title', 'Payment Methods')}
                </Text>
                <Text style={{ color: colors.textMuted, fontSize: 13, marginTop: 4 }} data-testid="payment-cards-subtitle" testID="payment-cards-subtitle">
                  {cards.length} {tx('paymentCards.subtitle.cardsSaved', cards.length === 1 ? 'card saved' : 'cards saved')} • {validCardsCount} {tx('paymentCards.subtitle.checkoutReady', 'checkout-ready')}
                </Text>
              </View>
            </View>

            <TouchableOpacity
              onPress={() => { setShowAdd(!showAdd); setEditingId(null); setRemovingId(null); resetForm(); }}
              style={{
                alignSelf: isMobile ? 'flex-start' : 'center',
                flexDirection: 'row',
                alignItems: 'center',
                gap: 8,
                backgroundColor: showAdd ? 'transparent' : colors.primary,
                paddingHorizontal: 18,
                paddingVertical: 11,
                borderRadius: 999,
                borderWidth: 1,
                borderColor: showAdd ? colors.border : colors.primary,
              }}
              data-testid="add-card-toggle"
              testID="add-card-toggle"
            >
              <Ionicons name={showAdd ? 'close' : 'add'} size={17} color={showAdd ? colors.textMuted : colors.primaryText} />
              <Text style={{ color: showAdd ? colors.textMuted : colors.primaryText, fontWeight: '800', fontSize: 13 }}>
                {showAdd ? tx('paymentCards.action.cancel', 'Cancel') : tx('paymentCards.action.addCard', 'Add Card')}
              </Text>
            </TouchableOpacity>
          </View>

          <View style={{ marginTop: 14, flexDirection: isDesktop ? 'row' : 'column', gap: 10 }}>
            <MetricTile
              title={tx('paymentCards.metrics.totalCards', 'Total Cards')}
              value={String(cards.length)}
              helper={tx('paymentCards.metrics.totalCardsHelper', 'Stored tokenized cards')}
              icon="albums"
              color={colors.primary}
              testId="payment-cards-metric-total"
            />
            <MetricTile
              title={tx('paymentCards.metrics.defaultCard', 'Default Card')}
              value={defaultCard ? `${String(defaultCard.card_type || 'card').toUpperCase()} •••• ${defaultCard.last_four}` : tx('paymentCards.metrics.none', 'None')}
              helper={tx('paymentCards.metrics.defaultCardHelper', 'Primary checkout card')}
              icon="star"
              color={colors.warning}
              testId="payment-cards-metric-default"
            />
            <MetricTile
              title={tx('paymentCards.metrics.validity', 'Validity Health')}
              value={`${validCardsCount}/${cards.length || 0}`}
              helper={expiringCardsCount > 0 ? `${expiringCardsCount} ${tx('paymentCards.metrics.expiringSoon', 'expiring soon')}` : tx('paymentCards.metrics.allHealthy', 'All active cards healthy')}
              icon={expiringCardsCount > 0 ? 'alert-circle' : 'shield-checkmark'}
              color={expiringCardsCount > 0 ? colors.warning : colors.success}
              testId="payment-cards-metric-validity"
            />
          </View>
        </View>

        <View style={{ flexDirection: isDesktop ? 'row' : 'column', gap: 12, marginBottom: 16 }}>
          <View
            style={{ flex: 1, backgroundColor: colors.successSoft, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.successSoft }}
            data-testid="payment-cards-security-banner"
            testID="payment-cards-security-banner"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <Ionicons name="shield-checkmark" size={18} color={colors.successText} />
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>
                {tx('paymentCards.security.title', 'Security and Compliance')}
              </Text>
            </View>
            <Text style={{ color: colors.textMuted, fontSize: 12, lineHeight: 19, marginTop: 8 }}>
              {tx('paymentCards.security.copy', 'Card details are collected securely via Stripe. Card numbers never touch platform servers.')}
            </Text>
          </View>

          <View
            style={{ flex: 1, backgroundColor: colors.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border }}
            data-testid="payment-cards-gateway-compatibility-card"
            testID="payment-cards-gateway-compatibility-card"
          >
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800', marginBottom: 8 }}>
              {tx('paymentCards.gateway.title', 'Checkout compatibility from platform data')}
            </Text>
            {observedGateways.length > 0 ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                {observedGateways.map((gateway) => (
                  <View
                    key={gateway}
                    style={{ backgroundColor: `${colors.primary}14`, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, borderWidth: 1, borderColor: `${colors.primary}44` }}
                    data-testid={`payment-cards-gateway-chip-${gateway}`}
                    testID={`payment-cards-gateway-chip-${gateway}`}
                  >
                    <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{formatGatewayLabel(gateway)}</Text>
                  </View>
                ))}
              </View>
            ) : (
              <Text style={{ color: colors.textMuted, fontSize: 11 }} data-testid="payment-cards-gateway-empty-note" testID="payment-cards-gateway-empty-note">
                {tx('paymentCards.gateway.empty', 'Gateway compatibility appears after your first active card is available.')}
              </Text>
            )}
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 10 }} data-testid="payment-cards-validity-note" testID="payment-cards-validity-note">
              {tx('paymentCards.gateway.note', 'Only valid, non-expired cards are available for checkout usage.')}
            </Text>
          </View>
        </View>

        {/* Toast */}
        {toast && (
          <View
            style={{
              backgroundColor: toast.type === 'success' ? colors.successSoft : colors.errorSoft,
              borderRadius: 10, padding: 12, marginBottom: 16, flexDirection: 'row', alignItems: 'center', gap: 8,
              borderWidth: 1, borderColor: toast.type === 'success' ? colors.successSoft : colors.errorSoft,
            }}
            data-testid={toast.type === 'success' ? 'card-success-msg' : 'card-error-msg'} testID={toast.type === 'success' ? 'card-success-msg' : 'card-error-msg'}
          >
            <Ionicons name={toast.type === 'success' ? 'checkmark-circle' : 'alert-circle'} size={16} color={toast.type === 'success' ? colors.success : colors.error} />
            <Text style={{ color: toast.type === 'success' ? colors.success : colors.error, fontSize: 13, flex: 1, fontWeight: '500' }}>{toast.msg}</Text>
            <TouchableOpacity onPress={() => setToast(null)} data-testid="dismiss-toast" testID="dismiss-toast">
              <Ionicons name="close" size={14} color={colors.textMuted} />
            </TouchableOpacity>
          </View>
        )}

        {/* ── Add Card Form (Stripe Elements) ── */}
        {showAdd && (
          <View style={{ backgroundColor: colors.card, borderRadius: 16, padding: isMobile ? 16 : 22, marginBottom: 20, borderWidth: 1, borderColor: colors.border }} data-testid="add-card-form" testID="add-card-form">
            <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800', marginBottom: 6 }}>{tx('paymentCards.addForm.title', 'Add New Card')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginBottom: 14 }} data-testid="payment-cards-add-form-subtitle" testID="payment-cards-add-form-subtitle">
              {tx('paymentCards.addForm.subtitle', 'Securely tokenize card details and keep checkout fast across supported providers.')}
            </Text>

            {stripeInitError && (
              <View style={{ backgroundColor: colors.errorSoft, borderRadius: 8, padding: 12, marginBottom: 14, borderWidth: 1, borderColor: colors.errorSoft }}>
                <Text style={{ color: colors.error, fontSize: 12 }}>{stripeInitError}</Text>
              </View>
            )}

            {/* Cardholder Name */}
            <FieldLabel label={tx('paymentCards.field.cardholderName', 'Cardholder Name')} error={fieldErrors.cardholder_name} colors={colors} />
            <TextInput
              value={form.cardholder_name}
              onChangeText={v => { setForm(f => ({ ...f, cardholder_name: v })); setFieldErrors(e => ({ ...e, cardholder_name: undefined })); }}
              placeholder={tx('paymentCards.field.cardholderPlaceholder', 'Full name on card')}
              placeholderTextColor={colors.textMuted}
              style={inputStyle(colors, !!fieldErrors.cardholder_name)}
              data-testid="card-holder-input" testID="card-holder-input"
            />

            {/* Stripe Card Element (secure iframe — number, expiry, CVC handled by Stripe) */}
            <FieldLabel label={tx('paymentCards.field.cardDetails', 'Card Details')} colors={colors} />
            <StripeCardInput
              colors={colors}
              darkMode={darkMode}
              onReady={handleCardElementReady}
              onError={handleStripeInitError}
            />
            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 6, marginBottom: 4 }}>{tx('paymentCards.field.cardDetailsNote', 'Card number, expiry, and CVC are securely collected by Stripe.')}</Text>

            {/* Submit */}
            <TouchableOpacity
              onPress={handleAdd}
              disabled={saving || !stripeReady}
              style={{
                backgroundColor: (saving || !stripeReady) ? colors.textSec : colors.primary, borderRadius: 10,
                paddingVertical: 14, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8,
                marginTop: 8, opacity: (saving || !stripeReady) ? 0.7 : 1,
              }}
              data-testid="save-card-btn" testID="save-card-btn"
            >
              {saving ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="lock-closed" size={15} color={colors.primaryText} />}
              <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 14 }}>
                {saving ? tx('paymentCards.action.verifying', 'Verifying...') : !stripeReady ? tx('paymentCards.action.loading', 'Loading...') : tx('paymentCards.action.addCardSecurely', 'Add Card Securely')}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Card List ── */}
        {loading ? (
          <PaymentHistorySkeleton />
        ) : cards.length === 0 ? (
          <View style={{ backgroundColor: colors.card, padding: isMobile ? 24 : 48, borderRadius: 16, alignItems: 'center', borderWidth: 1, borderColor: colors.border }} data-testid="no-cards-placeholder" testID="no-cards-placeholder">
            <View style={{ width: 72, height: 72, borderRadius: 22, backgroundColor: `${colors.primary}10`, alignItems: 'center', justifyContent: 'center', marginBottom: 16 }}>
              <Ionicons name="card-outline" size={36} color={colors.textMuted} />
            </View>
            <Text style={{ color: colors.text, fontSize: 20, fontWeight: '800', marginBottom: 6 }} data-testid="payment-cards-empty-title" testID="payment-cards-empty-title">{tx('paymentCards.empty.title', 'No Saved Cards')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 13, textAlign: 'center', maxWidth: 340 }} data-testid="payment-cards-empty-copy" testID="payment-cards-empty-copy">
              {tx('paymentCards.empty.copy', 'Add a payment card for quick, secure, and enterprise-grade checkout across platform-supported payment providers.')}
            </Text>
            <TouchableOpacity
              onPress={() => { setShowAdd(true); setEditingId(null); setRemovingId(null); resetForm(); }}
              style={{ marginTop: 16, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: colors.primary, borderRadius: 999, paddingHorizontal: 18, paddingVertical: 10 }}
              data-testid="payment-cards-empty-add-card-btn"
              testID="payment-cards-empty-add-card-btn"
            >
              <Ionicons name="add" size={16} color={colors.primaryText} />
              <Text style={{ color: colors.primaryText, fontWeight: '800', fontSize: 12 }}>{tx('paymentCards.action.addFirstCard', 'Add First Card')}</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14 }} data-testid="payment-cards-list-label" testID="payment-cards-list-label">
              {tx('paymentCards.savedCards', 'Saved Cards')} ({cards.length})
            </Text>

            <View style={{ flexDirection: isDesktop ? 'row' : 'column', flexWrap: isDesktop ? 'wrap' : 'nowrap', justifyContent: 'space-between' }}>
              {cards.map((card) => (
                <View key={card.card_id} style={{ width: isDesktop ? '49.2%' : '100%' }}>
                  <CardItem
                    card={card}
                    colors={colors}
                    mono={mono}
                    tx={tx}
                    isEditing={editingId === card.card_id}
                    isRemoving={removingId === card.card_id}
                    isLoading={actionLoading === card.card_id}
                    form={form}
                    fieldErrors={fieldErrors}
                    onEdit={() => startEdit(card)}
                    onCancelEdit={cancelEdit}
                    onSaveEdit={() => handleUpdate(card.card_id)}
                    onRemoveClick={() => setRemovingId(card.card_id)}
                    onConfirmRemove={() => handleRemove(card.card_id)}
                    onCancelRemove={() => setRemovingId(null)}
                    onSetDefault={() => handleSetDefault(card.card_id)}
                    onFormChange={(field: FormField, val: string) => {
                      setForm(f => ({ ...f, [field]: val }));
                      setFieldErrors(e => ({ ...e, [field]: undefined }));
                    }}
                  />
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </AppShell>
  );
}

/* ── Field Label ── */
function FieldLabel({ label, error, colors }: { label: string; error?: string; colors: any }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6, marginTop: 12 }}>
      <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</Text>
      {error && <Text style={{ color: colors.error, fontSize: 11 }}>{error}</Text>}
    </View>
  );
}

/* ── Input style ── */
function inputStyle(colors: any, hasError: boolean): any {
  return {
    backgroundColor: colors.surfaceHover,
    borderRadius: 8,
    padding: 13,
    color: colors.text,
    fontSize: 14,
    borderWidth: 1,
    borderColor: hasError ? `${colors.error}15` : colors.border,
  };
}

/* ── Card Item ── */
function CardItem({
  card, colors, mono, tx, isEditing, isRemoving, isLoading,
  form, fieldErrors,
  onEdit, onCancelEdit, onSaveEdit,
  onRemoveClick, onConfirmRemove, onCancelRemove,
  onSetDefault, onFormChange,
}: {
  card: CardData; colors: any; mono: string | undefined;
  tx: (key: string, fallback: string) => string;
  isEditing: boolean; isRemoving: boolean; isLoading: boolean;
  form: any; fieldErrors: any;
  onEdit: () => void; onCancelEdit: () => void; onSaveEdit: () => void;
  onRemoveClick: () => void; onConfirmRemove: () => void; onCancelRemove: () => void;
  onSetDefault: () => void;
  onFormChange: (field: FormField, val: string) => void;
}) {
  const brand = BRANDS[card.card_type] || BRANDS.other;
  const brandBg = (colors as any)[brand.bgTone] || colors.primary;
  const brandMarker = (colors as any)[brand.markerTone] || colors.primaryText;

  return (
    <View style={{ marginBottom: 18 }} data-testid={`card-${card.card_id}`} testID={`card-${card.card_id}`}>
      {/* Card Visual */}
      <View style={{
        backgroundColor: brandBg, borderRadius: 16, padding: 20,
        position: 'relative', overflow: 'hidden',
        ...(Platform.OS === 'web' ? { boxShadow: `0 6px 24px ${brandBg}50` } : {}),
      }}>
        {/* Decorative circles */}
        <View style={{ position: 'absolute', top: -20, right: -20, width: 100, height: 100, borderRadius: 50, backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '08') }} />
        <View style={{ position: 'absolute', bottom: -30, left: -10, width: 80, height: 80, borderRadius: 40, backgroundColor: (globalThis as any).__alphaColor(colors.primaryText, '05') }} />

        {/* Top row: brand + default badge */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 22 }}>
          <Text style={{ color: brandMarker, fontSize: 14, fontWeight: '800', letterSpacing: 1, opacity: 0.9 }}>{brand.label}</Text>
          {card.is_default && (
            <View style={{ backgroundColor: colors.success, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 }} data-testid={`default-badge-${card.card_id}`} testID={`default-badge-${card.card_id}`}>
              <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '800', letterSpacing: 0.5 }}>{tx('paymentCards.card.default', 'DEFAULT')}</Text>
            </View>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 6, marginBottom: 10 }}>
          <View
            style={{
              backgroundColor: card.validity_status === 'expiring_soon' ? colors.warningSoft : colors.successSoft,
              borderRadius: 6,
              paddingHorizontal: 8,
              paddingVertical: 4,
              borderWidth: 1,
              borderColor: card.validity_status === 'expiring_soon' ? colors.warningSoft : colors.successSoft,
            }}
            data-testid={`card-validity-${card.card_id}`} testID={`card-validity-${card.card_id}`}
          >
            <Text style={{ color: card.validity_status === 'expiring_soon' ? colors.warning : colors.success, fontSize: 9, fontWeight: '800' }}>
              {card.validity_status === 'expiring_soon' ? tx('paymentCards.card.expiringSoon', 'EXPIRING SOON') : tx('paymentCards.card.validCheckout', 'VALID FOR CHECKOUT')}
            </Text>
          </View>
        </View>

        {/* Card number */}
        <Text style={{ color: colors.primaryText + 'DD', fontSize: 20, fontWeight: '600', letterSpacing: 3, marginBottom: 22, fontFamily: mono }}>
          {card.masked_number}
        </Text>

        {/* Bottom row */}
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <View>
            <Text style={{ color: colors.primaryText + '45', fontSize: 9, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('paymentCards.card.cardholder', 'Card Holder')}</Text>
            <Text style={{ color: colors.primaryText + 'CC', fontSize: 13, fontWeight: '600', marginTop: 3 }}>{card.cardholder_name}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={{ color: colors.primaryText + '45', fontSize: 9, textTransform: 'uppercase', letterSpacing: 1 }}>{tx('paymentCards.card.expires', 'Expires')}</Text>
            <Text style={{ color: colors.primaryText + 'CC', fontSize: 13, fontWeight: '600', marginTop: 3 }}>
              {String(card.expiry_month).padStart(2, '0')}/{String(card.expiry_year).slice(-2)}
            </Text>
          </View>
        </View>
      </View>

      {/* Action buttons */}
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
        {!card.is_default && (
          <ActionButton
            testId={`set-default-${card.card_id}`}
            icon="star" iconColor={colors.warning}
            label={tx('paymentCards.action.setDefault', 'Set Default')}
            colors={colors}
            loading={isLoading}
            onPress={onSetDefault}
          />
        )}
        <ActionButton
          testId={`edit-card-${card.card_id}`}
          icon={isEditing ? 'close-circle' : 'create'}
          iconColor={colors.primary}
          label={isEditing ? tx('paymentCards.action.cancel', 'Cancel') : tx('paymentCards.action.edit', 'Edit')}
          colors={colors}
          active={isEditing}
          activeColor={`${colors.primary}15`}
          onPress={isEditing ? onCancelEdit : onEdit}
        />
        {isRemoving ? (
          <>
            <ActionButton
              testId={`remove-card-${card.card_id}`}
              icon="checkmark-circle" iconColor={colors.error}
              label={tx('paymentCards.action.confirm', 'Confirm')}
              colors={colors}
              active activeColor={`${colors.error}15`}
              loading={isLoading}
              onPress={onConfirmRemove}
            />
            <ActionButton
              testId={`cancel-remove-${card.card_id}`}
              icon="close" iconColor={colors.textMuted}
              label={tx('paymentCards.action.cancel', 'Cancel')}
              colors={colors}
              onPress={onCancelRemove}
            />
          </>
        ) : (
          <ActionButton
            testId={`remove-btn-${card.card_id}`}
            icon="trash" iconColor={colors.error}
            label={tx('paymentCards.action.remove', 'Remove')}
            colors={colors}
            onPress={onRemoveClick}
          />
        )}
      </View>

      {/* Edit form */}
      {isEditing && (
        <View style={{ backgroundColor: colors.surface, borderRadius: 12, padding: 16, marginTop: 10, borderWidth: 1, borderColor: `${colors.primary}25` }} data-testid={`edit-form-${card.card_id}`} testID={`edit-form-${card.card_id}`}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginBottom: 4 }}>{tx('paymentCards.edit.title', 'Update Card Details')}</Text>

          <FieldLabel label={tx('paymentCards.field.cardholderName', 'Cardholder Name')} error={fieldErrors.cardholder_name} colors={colors} />
          <TextInput
            value={form.cardholder_name}
            onChangeText={(v: string) => onFormChange('cardholder_name', v)}
            style={inputStyle(colors, !!fieldErrors.cardholder_name)}
            data-testid={`edit-name-${card.card_id}`} testID={`edit-name-${card.card_id}`}
          />

          <FieldLabel label={tx('paymentCards.field.newExpiry', 'New Expiry (MM/YY)')} error={fieldErrors.expiry} colors={colors} />
          <TextInput
            value={form.expiry}
            onChangeText={(v: string) => onFormChange('expiry', fmtExpiry(v))}
            placeholder={tx('paymentCards.field.expiryPlaceholder', 'MM/YY')}
            placeholderTextColor={colors.textMuted}
            keyboardType="numeric"
            maxLength={5}
            style={{ ...inputStyle(colors, !!fieldErrors.expiry), width: 110, letterSpacing: 2 }}
            data-testid={`edit-expiry-${card.card_id}`} testID={`edit-expiry-${card.card_id}`}
          />

          <TouchableOpacity
            onPress={onSaveEdit}
            disabled={isLoading}
            style={{
              backgroundColor: isLoading ? colors.borderBright : colors.primary, borderRadius: 8,
              paddingVertical: 12, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6,
              marginTop: 14, opacity: isLoading ? 0.7 : 1,
            }}
            data-testid={`save-edit-${card.card_id}`} testID={`save-edit-${card.card_id}`}
          >
            {isLoading ? <ActivityIndicator size="small" color={colors.primaryText} /> : <Ionicons name="checkmark" size={16} color={colors.primaryText} />}
            <Text style={{ color: colors.primaryText, fontWeight: '700', fontSize: 13 }}>{isLoading ? tx('paymentCards.action.saving', 'Saving...') : tx('paymentCards.action.saveChanges', 'Save Changes')}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

/* ── Action Button ── */
function ActionButton({ testId, icon, iconColor, label, colors, active, activeColor, loading, onPress }: {
  testId: string; icon: string; iconColor: string; label: string; colors: any;
  active?: boolean; activeColor?: string; loading?: boolean; onPress: () => void;
}) {
  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={loading}
      style={{
        flex: 1, backgroundColor: active ? (activeColor || colors.surface) : colors.surface,
        borderRadius: 8, paddingVertical: 9, alignItems: 'center',
        flexDirection: 'row', justifyContent: 'center', gap: 5,
        borderWidth: 1, borderColor: active ? `${iconColor}30` : colors.border,
        opacity: loading ? 0.6 : 1,
      }}
      data-testid={testId} testID={testId}
    >
      {loading ? <ActivityIndicator size={12} color={iconColor} /> : <Ionicons name={icon as any} size={13} color={iconColor} />}
      <Text style={{ color: colors.text, fontWeight: '600', fontSize: 11 }}>{label}</Text>
    </TouchableOpacity>
  );
}