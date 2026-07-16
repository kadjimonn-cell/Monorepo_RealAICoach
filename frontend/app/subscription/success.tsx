import React, { useEffect, useState, useRef, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useTheme } from '../../src/context/ThemeContext';
import api from '../../src/services/api';
import AppShell from '../../src/components/AppShell';
import { SubscriptionFlowSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useTranslation } from '../../src/hooks/useTranslation';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { normalizeReturnTarget } from '../../src/utils/subscriptionReturnTarget';
import { useAuth } from '../../src/context/AuthContext';
import { useAccessControl } from '../../src/context/AccessControlContext';
import { stashSubscriptionReturnToast } from '../../src/utils/subscriptionReturnToast';
import { SubscriptionSuccessPanel } from '../../src/components/payment/SubscriptionSuccessPanel';
import { SubscriptionUnlockedDestinationSummary } from '../../src/components/payment/SubscriptionUnlockedDestinationSummary';
import { getPaymentFailureCopy } from '../../src/utils/paymentFailureCopy';

type PaymentState = 'verifying' | 'capturing' | 'success' | 'failed' | 'cancelled' | 'expired' | 'unknown';
type PaymentProvider = 'stripe' | 'paypal' | 'unknown';

export default function PaymentSuccessPage() {
  const pageReady = usePageReady();
  const router = useRouter();
  const params = useLocalSearchParams<{ session_id?: string; token?: string; PayerID?: string; return_to?: string }>();
  const {isDarkMode, colors} = useTheme();
  const { refreshUser } = useAuth();
  const { refresh: refreshAccessControl } = useAccessControl();
  const { width } = useWindowDimensions();
  const isCompact = width < 420;
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  // @autofix-moved: was module-level const STATE_CONFIG
  const STATE_CONFIG: Record<PaymentState, { icon: string; color: string; title: string }> = {
    verifying: { icon: 'hourglass', color: colors.primary, title: tx('subscriptionSuccess.states.verifying.title', 'Verifying Payment') },
    capturing: { icon: 'hourglass', color: colors.primary, title: tx('subscriptionSuccess.states.capturing.title', 'Completing Payment') },
    success: { icon: 'checkmark-circle', color: colors.successText, title: tx('subscriptionSuccess.states.success.title', 'Payment Successful!') },
    failed: { icon: 'close-circle', color: colors.error, title: getPaymentFailureCopy('failed', providerLabel, tx).title },
    cancelled: { icon: 'remove-circle', color: colors.warningText, title: getPaymentFailureCopy('cancelled', providerLabel, tx).title },
    expired: { icon: 'time', color: colors.warningText, title: getPaymentFailureCopy('expired', providerLabel, tx).title },
    unknown: { icon: 'help-circle', color: colors.textMuted, title: getPaymentFailureCopy('unknown', providerLabel, tx).title },
  };
  const [state, setState] = useState<PaymentState>('verifying');
  const [provider, setProvider] = useState<PaymentProvider>('unknown');
  const [details, setDetails] = useState<{ amount?: number; currency?: string; plan?: string; ticket?: string } | null>(null);
  const pollRef = useRef(0);
  const capturedRef = useRef(false);
  const maxPolls = 15;
  const providerLabel = provider === 'paypal' ? 'PayPal' : provider === 'stripe' ? 'Stripe' : 'Payment Gateway';
  const stateMessages: Record<PaymentState, string> = {
    verifying: 'Confirming your payment. This usually takes just a few seconds...',
    capturing: 'Finalizing your PayPal payment. Please wait...',
    success: 'Your subscription has been activated. A confirmation email with your eTicket is on its way.',
    failed: getPaymentFailureCopy('failed', providerLabel, tx).message,
    cancelled: getPaymentFailureCopy('cancelled', providerLabel, tx).message,
    expired: getPaymentFailureCopy('expired', providerLabel, tx).message,
    unknown: getPaymentFailureCopy('unknown', providerLabel, tx).message,
  };

  const dm = isDarkMode;
  const bg = dm ? colors.bgAlt : colors.bg;
  const card = dm ? colors.cardMuted : colors.card;
  const txt = colors.text;
  const txtSec = colors.textMuted;
  const brd = dm ? colors.border : colors.border;

  const config = STATE_CONFIG[state];
  const smartReturnTarget = normalizeReturnTarget(String(params.return_to || '/dashboard'));

  // ── PayPal capture flow ──
  const capturePayPal = useCallback(async (orderId: string) => {
    if (capturedRef.current) return;
    capturedRef.current = true;
    setState('capturing');
    try {
      const res = await api.post('/subscriptions/paypal/capture', { order_id: orderId });
      if (res.data?.success || res.data?.status === 'COMPLETED') {
        await refreshUser();
        await refreshAccessControl();
        setDetails({
          plan: res.data.subscription_plan,
          ticket: res.data.ticket_id,
        });
        setState('success');
      } else {
        setState('failed');
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || '';
      if (msg.includes('already been captured') || msg.includes('COMPLETED')) {
        setState('success');
      } else {
        setState('failed');
      }
    }
  }, [refreshAccessControl, refreshUser]);

  // ── Stripe polling flow ──
  const pollStripe = useCallback(async (sessionId: string) => {
    try {
      const res = await api.get(`/subscriptions/checkout-status/${sessionId}`);
      const { payment_status, amount_total, currency, status } = res.data;
      const normalizedPaymentStatus = String(payment_status || '').toLowerCase();
      const normalizedStatus = String(status || '').toLowerCase();
      setDetails({ amount: amount_total ? amount_total / 100 : undefined, currency: currency?.toUpperCase() });

      if (['paid', 'completed', 'succeeded'].includes(normalizedPaymentStatus)) {
        await refreshUser();
        await refreshAccessControl();
        setState('success');
      } else if (normalizedPaymentStatus === 'unpaid' && normalizedStatus === 'expired') {
        setState('expired');
      } else if (['failed', 'canceled', 'cancelled'].includes(normalizedPaymentStatus)) {
        setState('failed');
      }
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/success.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [refreshAccessControl, refreshUser]);

  useEffect(() => {
    const { session_id, token, PayerID } = params;

    // Detect provider from URL params
    if (token && PayerID) {
      // PayPal redirect: ?token=ORDER_ID&PayerID=XXXX
      setProvider('paypal');
      capturePayPal(token);
      return;
    }

    if (token && !PayerID) {
      // PayPal redirect without PayerID (user cancelled or partial)
      setProvider('paypal');
      setState('cancelled');
      return;
    }

    if (session_id) {
      // Stripe redirect: ?session_id=cs_xxx
      setProvider('stripe');
      pollStripe(session_id);
      const interval = setInterval(() => {
        pollRef.current += 1;
        if (pollRef.current >= maxPolls) {
          clearInterval(interval);
          setState(prev => prev === 'verifying' ? 'unknown' : prev);
          return;
        }
        pollStripe(session_id);
      }, 3000);
      return () => clearInterval(interval);
    }

    // No recognized params
    setState('unknown');
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const providerIcon = provider === 'paypal' ? 'logo-paypal' : 'card';

  if (!pageReady) return <SubscriptionFlowSkeleton />;
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: bg }}>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: isCompact ? 14 : 24 }}>
          <View
            data-testid="payment-success-card" testID="payment-success-card"
            style={{
              width: '100%', maxWidth: 480, backgroundColor: card,
              borderRadius: 20, borderWidth: 1, borderColor: brd,
              padding: isCompact ? 20 : 32, alignItems: 'center',
            }}
          >
            {(state === 'verifying' || state === 'capturing') ? (
              <>
                <View
                  style={{
                    width: isCompact ? 68 : 80, height: isCompact ? 68 : 80, borderRadius: isCompact ? 34 : 40,
                    backgroundColor: (globalThis as any).__alphaColor(config.color, '18'),
                    justifyContent: 'center', alignItems: 'center', marginBottom: 20,
                  }}
                >
                  <ActivityIndicator size="large" color={config.color} />
                </View>
                <Text data-testid="payment-success-title" testID="payment-success-title" style={{ fontSize: isCompact ? 19 : 22, fontWeight: '800', color: txt, textAlign: 'center', marginBottom: 8 }}>{config.title}</Text>
                <Text data-testid="payment-success-message" testID="payment-success-message" style={{ fontSize: isCompact ? 13 : 14, color: txtSec, textAlign: 'center', lineHeight: isCompact ? 20 : 22, marginBottom: 20 }}>{stateMessages[state]}</Text>
              </>
            ) : state === 'success' ? (
              <SubscriptionSuccessPanel
                amountText={details?.amount ? `${details.currency === 'USD' ? '$' : (details.currency || '') + ' '}${details.amount.toFixed(2)}` : null}
                badgeText={details?.ticket ? `${tx('autofix.batch9.eticket', 'eTicket:')} ${details.ticket}` : `${tx('autofix.batch9.paid.via', 'Paid via')} ${providerLabel}`}
                ctaLabel={tx('paymentResult.actions.goDashboard', 'Go to Dashboard')}
                colors={{
                  success: colors.success,
                  successText: colors.successText,
                  successSoft: colors.successSoft,
                  text: txt,
                  textMuted: txtSec,
                  border: brd,
                  bgSoft: colors.bgSoft,
                  primaryText: colors.primaryText,
                }}
                historyLabel={tx('paymentResult.actions.viewHistory', 'View Payment History')}
                onPressCta={() => { stashSubscriptionReturnToast(smartReturnTarget, details?.plan || null); router.replace(smartReturnTarget as any); }}
                onPressHistory={() => router.replace('/payment-history')}
                preCtaContent={(
                  <SubscriptionUnlockedDestinationSummary
                    colors={{
                      success: colors.success,
                      successText: colors.successText,
                      text: txt,
                      textMuted: txtSec,
                      bgSoft: colors.bgSoft,
                    }}
                    planName={details?.plan || null}
                    providerKey={provider}
                    providerLabel={providerLabel}
                    returnTarget={smartReturnTarget}
                    testIdPrefix="payment-redirect-unlocked"
                    tx={tx}
                  />
                )}
                subtitle={stateMessages[state]}
                title={config.title}
              />
            ) : (
              <>
                <View
                  style={{
                    width: isCompact ? 68 : 80, height: isCompact ? 68 : 80, borderRadius: isCompact ? 34 : 40,
                    backgroundColor: (globalThis as any).__alphaColor(config.color, '18'),
                    justifyContent: 'center', alignItems: 'center', marginBottom: 20,
                  }}
                >
                  <Ionicons name={config.icon as any} size={44} color={config.color} />
                </View>
                <Text data-testid="payment-success-title" testID="payment-success-title" style={{ fontSize: isCompact ? 19 : 22, fontWeight: '800', color: txt, textAlign: 'center', marginBottom: 8 }}>{config.title}</Text>
                <Text data-testid="payment-success-message" testID="payment-success-message" style={{ fontSize: isCompact ? 13 : 14, color: txtSec, textAlign: 'center', lineHeight: isCompact ? 20 : 22, marginBottom: 20 }}>{stateMessages[state]}</Text>
              </>
            )}

            {/* Provider badge */}
            <View
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                paddingHorizontal: 12, paddingVertical: 6, borderRadius: 99,
                backgroundColor: dm ? colors.border : colors.bgSoft, marginBottom: 16,
              }}
            >
              <Ionicons name={providerIcon as any} size={14} color={txtSec} />
              <Text style={{ fontSize: 11, fontWeight: '600', color: txtSec }}>
                {tx('autofix.batch9.paid.via', 'Paid via')} {providerLabel}
              </Text>
            </View>

            {/* Verifying spinner */}
            {(state === 'verifying' || state === 'capturing') && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <ActivityIndicator size="small" color={config.color} />
                <Text style={{ fontSize: 12, color: config.color, fontWeight: '600' }}>
                  {state === 'capturing' ? 'Finalizing with PayPal...' : `Confirming with ${providerLabel}...`}
                </Text>
              </View>
            )}

            {/* Action Buttons */}
            <View style={{ width: '100%', gap: 10, marginTop: 8 }}>
              {(state === 'failed' || state === 'cancelled' || state === 'expired' || state === 'unknown') && (
                <TouchableOpacity
                  data-testid="payment-success-retry" testID="payment-success-retry"
                  onPress={() => router.replace({ pathname: '/subscription/plans', params: { status: state, gateway: provider } })}
                  style={{
                    backgroundColor: colors.primary, borderRadius: 12,
                    paddingVertical: 14, alignItems: 'center',
                  }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: isCompact ? 13 : 14, fontWeight: '700' }}>
                    {state === 'expired' ? 'View Plans' : 'Try Again'}
                  </Text>
                </TouchableOpacity>
              )}

              {state !== 'success' ? (
                <TouchableOpacity
                  data-testid="payment-success-view-history" testID="payment-success-view-history"
                  onPress={() => router.replace('/payment-history')}
                  style={{
                    backgroundColor: 'transparent', borderRadius: 12,
                    borderWidth: 1, borderColor: brd,
                    paddingVertical: 14, alignItems: 'center',
                  }}
                >
                  <Text style={{ color: txtSec, fontSize: isCompact ? 13 : 14, fontWeight: '700' }}>View Payment History</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        </View>
      </SafeAreaView>
    </AppShell>
  );
}
