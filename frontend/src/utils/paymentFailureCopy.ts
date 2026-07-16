export type PaymentFailureState = 'cancelled' | 'failed' | 'refunded' | 'expired' | 'unknown';

type TranslateFn = (key: string, fallback: string) => string;

export function normalizePaymentFailureState(value?: string | null): PaymentFailureState {
  const normalized = String(value || '').trim().toLowerCase();

  if (['cancelled', 'canceled'].includes(normalized)) return 'cancelled';
  if (['refunded', 'reversed', 'revoked'].includes(normalized)) return 'refunded';
  if (['expired', 'inactive'].includes(normalized)) return 'expired';
  if (['failed', 'declined', 'denied', 'unpaid'].includes(normalized)) return 'failed';
  return 'unknown';
}

export function getPaymentFailureCopy(state: PaymentFailureState, gatewayLabel: string, tx: TranslateFn) {
  const provider = gatewayLabel || tx('subscriptionPlans.banner.gateway.generic', 'Payment Gateway');

  const copyMap: Record<PaymentFailureState, { title: string; message: string; tone: 'warning' | 'error' }> = {
    cancelled: {
      tone: 'warning',
      title: tx('subscriptionPlans.banner.cancelled.title', 'Checkout cancelled'),
      message: tx('subscriptionPlans.banner.cancelled.message', `${provider} checkout was cancelled before payment completed. No charge was completed.`)
        .replace('${gatewayLabel}', provider),
    },
    failed: {
      tone: 'error',
      title: tx('subscriptionPlans.banner.failed.title', 'Payment not completed'),
      message: tx('subscriptionPlans.banner.failed.message', `${provider} could not complete your payment. No charge was completed. Try again or choose a different method.`)
        .replace('${gatewayLabel}', provider),
    },
    refunded: {
      tone: 'warning',
      title: tx('subscriptionPlans.banner.refunded.title', 'Payment refunded'),
      message: tx('subscriptionPlans.banner.refunded.message', `${provider} marked this payment as refunded. Review payment history for the latest billing status.`)
        .replace('${gatewayLabel}', provider),
    },
    expired: {
      tone: 'warning',
      title: tx('subscriptionPlans.banner.expired.title', 'Checkout expired'),
      message: tx('subscriptionPlans.banner.expired.message', `${provider} checkout expired before payment completed. Please start again from your plan selection.`)
        .replace('${gatewayLabel}', provider),
    },
    unknown: {
      tone: 'warning',
      title: tx('subscriptionPlans.banner.unknown.title', 'Payment status pending review'),
      message: tx('subscriptionPlans.banner.unknown.message', `We could not confirm the final payment status from ${provider}. Review payment history or try again.`)
        .replace('${gatewayLabel}', provider),
    },
  };

  return copyMap[state];
}