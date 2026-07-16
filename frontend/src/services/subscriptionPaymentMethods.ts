import api from './api';

export type PaymentMethodId = 'stripe' | 'paypal' | 'fedapay' | 'apple_iap' | 'google_iap';

export type GatewayConfigPayload = {
  stripe_available?: boolean;
  stripe_publishable_key?: string;
  stripe_mode?: string;
  paypal_available?: boolean;
  paypal_client_id?: string;
  paypal_mode?: string;
  fedapay_available?: boolean;
  fedapay_public_key?: string;
  apple_iap_available?: boolean;
  google_iap_available?: boolean;
  apple_iap_status_label?: string;
  google_iap_status_label?: string;
};

export type PaymentMethodAvailability = {
  id: PaymentMethodId;
  available: boolean;
  reason: string;
};

export const resolvePaymentMethodsFromGatewayConfig = (
  payload?: GatewayConfigPayload | null,
): Record<PaymentMethodId, PaymentMethodAvailability> => {
  const cfg = payload || {};

  const stripeConfigured = Boolean(cfg.stripe_available) && Boolean(String(cfg.stripe_publishable_key || '').trim());
  const paypalConfigured = Boolean(cfg.paypal_available) && Boolean(String(cfg.paypal_client_id || '').trim());
  const fedapayConfigured = Boolean(cfg.fedapay_available);
  const appleIapConfigured = Boolean(cfg.apple_iap_available);
  const googleIapConfigured = Boolean(cfg.google_iap_available);

  return {
    stripe: {
      id: 'stripe',
      available: stripeConfigured,
      reason: stripeConfigured ? 'Ready' : 'Stripe is not configured in gateway settings',
    },
    paypal: {
      id: 'paypal',
      available: paypalConfigured,
      reason: paypalConfigured ? 'Ready' : 'PayPal is not configured in gateway settings',
    },
    fedapay: {
      id: 'fedapay',
      available: fedapayConfigured,
      reason: fedapayConfigured ? 'Ready' : 'FedaPay is not configured in gateway settings',
    },
    apple_iap: {
      id: 'apple_iap',
      available: appleIapConfigured,
      reason: appleIapConfigured ? (String(cfg.apple_iap_status_label || '').trim() || 'Ready') : 'Apple IAP is not configured in gateway settings',
    },
    google_iap: {
      id: 'google_iap',
      available: googleIapConfigured,
      reason: googleIapConfigured ? (String(cfg.google_iap_status_label || '').trim() || 'Ready') : 'Google IAP is not configured in gateway settings',
    },
  };
};

export const fetchSubscriptionGatewayConfig = async (): Promise<GatewayConfigPayload> => {
  const { data } = await api.get(`/subscriptions/gateway-config?cb=${Date.now()}`);
  return (data || {}) as GatewayConfigPayload;
};
