import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, useWindowDimensions} from 'react-native';
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
import { getPaymentFailureCopy, normalizePaymentFailureState } from '../../src/utils/paymentFailureCopy';

export default function PaymentResultPage() {
  const pageReady = usePageReady();
  const router = useRouter();
  const { status: rawStatus, gateway, payment_id, _tx_id, return_to } = useLocalSearchParams<{
    status?: string; gateway?: string; payment_id?: string; tx_id?: string; return_to?: string;
  }>();
  const {isDarkMode, colors} = useTheme();
  const { refreshUser } = useAuth();
  const { refresh: refreshAccessControl } = useAccessControl();
  const { width } = useWindowDimensions();
  const isCompact = width < 420;
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const initialStatusParam = rawStatus?.toLowerCase() || 'pending';
  const normalizedInitialStatus = normalizePaymentFailureState(initialStatusParam);
  const fedapayCancelledCopy = getPaymentFailureCopy('cancelled', 'FedaPay', tx);
  const fedapayFailedCopy = getPaymentFailureCopy('failed', 'FedaPay', tx);
  const fedapayRefundedCopy = getPaymentFailureCopy('refunded', 'FedaPay', tx);
  const fedapayUnknownCopy = getPaymentFailureCopy('unknown', 'FedaPay', tx);

  // @autofix-moved: was module-level const STATUS_CONFIG
  const STATUS_CONFIG: Record<string, { icon: string; color: string; title: string; message: string }> = {
    approved: {
      icon: 'checkmark-circle',
      color: colors.successText,
      title: t('paymentResult.status.successTitle'),
      message: t('paymentResult.status.successMessage'),
    },
    completed: {
      icon: 'checkmark-circle',
      color: colors.successText,
      title: t('paymentResult.status.successTitle'),
      message: t('paymentResult.status.successMessage'),
    },
    pending: {
      icon: 'time',
      color: colors.warningText,
      title: t('paymentResult.status.processingTitle'),
      message: t('paymentResult.status.processingMessage'),
    },
    declined: {
      icon: 'close-circle',
      color: colors.error,
      title: t('paymentResult.status.declinedTitle'),
      message: t('paymentResult.status.declinedMessage'),
    },
    cancelled: {
      icon: 'close-circle',
      color: colors.warningText,
      title: t('paymentResult.status.cancelledTitle') || fedapayCancelledCopy.title,
      message: t('paymentResult.status.cancelledMessage') || fedapayCancelledCopy.message,
    },
    failed: {
      icon: 'alert-circle',
      color: colors.error,
      title: t('paymentResult.status.failedTitle') || fedapayFailedCopy.title,
      message: t('paymentResult.status.failedMessage') || fedapayFailedCopy.message,
    },
    refunded: {
      icon: 'reload-circle',
      color: colors.warningText,
      title: t('paymentResult.status.refundedTitle') || fedapayRefundedCopy.title,
      message: t('paymentResult.status.refundedMessage') || fedapayRefundedCopy.message,
    },
    unknown: {
      icon: 'help-circle',
      color: colors.textMuted,
      title: t('paymentResult.status.unknownTitle') || fedapayUnknownCopy.title,
      message: t('paymentResult.status.unknownMessage') || fedapayUnknownCopy.message,
    },
  };
  const [currentStatus, setCurrentStatus] = useState(
    ['approved', 'completed', 'pending'].includes(initialStatusParam) ? initialStatusParam : normalizedInitialStatus,
  );
  const [_polling, setPolling] = useState(false);
  const pollCount = useRef(0);

  const dm = isDarkMode;
  const bg = dm ? colors.bgAlt : colors.bg;
  const card = dm ? colors.card : colors.card;
  const text = colors.text;
  const textSec = colors.textMuted;
  const border = dm ? colors.border : colors.border;

  const config = STATUS_CONFIG[currentStatus] || STATUS_CONFIG[normalizedInitialStatus] || STATUS_CONFIG.unknown;
  const smartReturnTarget = normalizeReturnTarget(String(return_to || '/dashboard'));

  // Poll for pending payments
  const pollStatus = useCallback(async () => {
    if (!payment_id || currentStatus !== 'pending') return;
    setPolling(true);
    try {
      const res = await api.get(`/fedapay/status/${payment_id}`);
      const newStatus = res.data?.status?.toLowerCase() || 'pending';
      if (newStatus !== 'pending') {
        if (newStatus === 'completed' || newStatus === 'approved') {
          await refreshUser();
          await refreshAccessControl();
        }
        setCurrentStatus(newStatus === 'completed' ? 'approved' : normalizePaymentFailureState(newStatus));
      }
    } catch (error) { handleAppRecoverableError({ scope: 'subscription/payment-result.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setPolling(false);
    }
  }, [currentStatus, payment_id, refreshAccessControl, refreshUser]);

  useEffect(() => {
    if (currentStatus !== 'pending') return;
    const interval = setInterval(() => {
      pollCount.current += 1;
      if (pollCount.current <= 12) pollStatus(); // Poll for 1 minute (every 5s x 12)
    }, 5000);
    // Initial poll
    pollStatus();
    return () => clearInterval(interval);
  }, [currentStatus, pollStatus]);

  if (!pageReady) return <SubscriptionFlowSkeleton />;
  return (
    <AppShell>
      <SafeAreaView style={{ flex: 1, backgroundColor: bg }}>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: isCompact ? 14 : 24 }}>
          <View
            data-testid="payment-result-card" testID="payment-result-card"
            style={{
              width: '100%', maxWidth: 480, backgroundColor: card,
              borderRadius: 20, borderWidth: 1, borderColor: border,
              padding: isCompact ? 20 : 32, alignItems: 'center',
            }}
          >
            {(currentStatus === 'approved' || currentStatus === 'completed') ? (
              <SubscriptionSuccessPanel
                amountText={null}
                badgeText={gateway ? `${t('paymentResult.via')} ${gateway === 'fedapay' ? t('paymentResult.gateway.fedapay') : gateway}` : null}
                ctaLabel={t('paymentResult.actions.goDashboard')}
                colors={{
                  success: colors.success,
                  successText: colors.successText,
                  successSoft: colors.successSoft,
                  text,
                  textMuted: textSec,
                  border,
                  bgSoft: colors.bgSoft,
                  primaryText: colors.primaryText,
                }}
                historyLabel={t('paymentResult.actions.viewHistory')}
                onPressCta={() => { stashSubscriptionReturnToast(smartReturnTarget, null); router.replace(smartReturnTarget as any); }}
                onPressHistory={() => router.replace('/payment-history')}
                preCtaContent={(
                  <SubscriptionUnlockedDestinationSummary
                    colors={{
                      success: colors.success,
                      successText: colors.successText,
                      text,
                      textMuted: textSec,
                      bgSoft: colors.bgSoft,
                    }}
                    planName={null}
                    providerKey={String(gateway || 'fedapay').toLowerCase() === 'fedapay' ? 'fedapay' : 'unknown'}
                    providerLabel={String(gateway || 'FedaPay')}
                    returnTarget={smartReturnTarget}
                    testIdPrefix="payment-result-unlocked"
                    tx={tx}
                  />
                )}
                subtitle={config.message}
                title={config.title}
              />
            ) : (
              <>
                <View style={{ width: isCompact ? 68 : 80, height: isCompact ? 68 : 80, borderRadius: isCompact ? 34 : 40, backgroundColor: (globalThis as any).__alphaColor(config.color, '18'), justifyContent: 'center', alignItems: 'center', marginBottom: 20 }}>
                  <Ionicons name={config.icon as any} size={44} color={config.color} />
                </View>
                <Text data-testid="payment-result-title" testID="payment-result-title" style={{ fontSize: isCompact ? 19 : 22, fontWeight: '800', color: text, textAlign: 'center', marginBottom: 8 }}>{config.title}</Text>
                <Text data-testid="payment-result-message" testID="payment-result-message" style={{ fontSize: isCompact ? 13 : 14, color: textSec, textAlign: 'center', lineHeight: isCompact ? 20 : 22, marginBottom: 20 }}>{config.message}</Text>
              </>
            )}

            {/* Gateway badge */}
            {gateway && (
              <View
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 6,
                  paddingHorizontal: 12, paddingVertical: 6, borderRadius: 99,
                  backgroundColor: dm ? colors.border : colors.bgSoft, marginBottom: 20,
                }}
              >
                <Text style={{ fontSize: 11, fontWeight: '600', color: textSec }}>
                  {t('paymentResult.via')} {gateway === 'fedapay' ? t('paymentResult.gateway.fedapay') : gateway}
                </Text>
              </View>
            )}

            {/* Polling indicator */}
            {currentStatus === 'pending' && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                <ActivityIndicator size="small" color={config.color} />
                <Text style={{ fontSize: 12, color: config.color, fontWeight: '600' }}>
                  {t('paymentResult.checkingStatus')}
                </Text>
              </View>
            )}

            {/* Action Buttons */}
            <View style={{ width: '100%', gap: 10, marginTop: 8 }}>
              {(['declined', 'failed', 'cancelled', 'refunded'] as string[]).includes(currentStatus) && (
                <TouchableOpacity
                  data-testid="payment-result-retry" testID="payment-result-retry"
                  onPress={() => router.replace({ pathname: '/subscription/plans', params: { status: currentStatus, gateway: String(gateway || 'fedapay') } })}
                  style={{
                    backgroundColor: colors.primary, borderRadius: 12,
                    paddingVertical: 14, alignItems: 'center',
                  }}
                >
                  <Text style={{ color: colors.primaryText, fontSize: isCompact ? 13 : 14, fontWeight: '700' }}>{t('common.tryAgain')}</Text>
                </TouchableOpacity>
              )}

              {(currentStatus !== 'approved' && currentStatus !== 'completed') ? (
                <TouchableOpacity
                  data-testid="payment-result-view-history" testID="payment-result-view-history"
                  onPress={() => router.replace('/payment-history')}
                  style={{
                    backgroundColor: 'transparent', borderRadius: 12,
                    borderWidth: 1, borderColor: border,
                    paddingVertical: 14, alignItems: 'center',
                  }}
                >
                  <Text style={{ color: textSec, fontSize: isCompact ? 13 : 14, fontWeight: '700' }}>{t('paymentResult.actions.viewHistory')}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        </View>
      </SafeAreaView>
    </AppShell>
  );
}
