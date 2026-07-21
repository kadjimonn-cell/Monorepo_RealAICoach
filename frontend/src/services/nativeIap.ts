import { Platform } from 'react-native';
import Constants from 'expo-constants';
import api from './api';

/**
 * Phase 3 — Native In-App Purchases (expo-iap, iOS StoreKit 2 / Google Play Billing).
 *
 * Server-side verification uses the EXISTING backend contracts:
 *   POST /api/iap/apple/verify   { transaction_id, receipt_data? }
 *   POST /api/iap/google/verify  { purchase_token, product_id }
 * Both return { success, plan, active, expires_at, auto_renewing, subscription_update }.
 *
 * Behavior matrix:
 *   - iOS/Android EAS dev/prod build : full purchase + restore flows.
 *   - Expo Go                        : 'unavailable' (native module cannot run).
 *   - Web                            : 'unavailable' (web keeps Stripe/PayPal/FedaPay).
 *
 * finishTransaction is called ONLY after successful backend verification
 * (playbook guidance: never acknowledge unverified purchases).
 */

export type IapPurchaseResult =
  | { status: 'success'; plan: string; active: boolean; expiresAt: string | null }
  | { status: 'unavailable'; reason: string }
  | { status: 'cancelled' }
  | { status: 'error'; message: string };

export type IapRestoreResult =
  | { status: 'success'; restoredCount: number; plan: string | null }
  | { status: 'unavailable'; reason: string }
  | { status: 'error'; message: string };

function isExpoGo(): boolean {
  const c: any = Constants;
  return c?.executionEnvironment === 'storeClient' || c?.appOwnership === 'expo';
}

export function isNativeIapSupported(): boolean {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return false;
  if (isExpoGo()) return false;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require('expo-iap');
    return true;
  } catch {
    return false;
  }
}

function isUserCancelledError(e: any): boolean {
  const code = String(e?.code || e?.responseCode || '').toLowerCase();
  const msg = String(e?.message || '').toLowerCase();
  return (
    code.includes('cancel') ||
    msg.includes('cancel') ||
    code === 'e_user_cancelled' ||
    code === '1' // Play Billing USER_CANCELED
  );
}

async function withConnection<T>(fn: (IAP: any) => Promise<T>): Promise<T> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const IAP: any = require('expo-iap');
  await IAP.initConnection();
  try {
    return await fn(IAP);
  } finally {
    try {
      await IAP.endConnection();
    } catch {
      // connection already closed
    }
  }
}

/** Version-tolerant subscription purchase request (expo-iap v4 unified API + fallbacks). */
async function requestSubscriptionCompat(IAP: any, sku: string): Promise<void> {
  if (typeof IAP.requestPurchase === 'function') {
    return IAP.requestPurchase({
      request: {
        ios: { sku },
        android: { skus: [sku] },
        sku,
        skus: [sku],
      },
      type: 'subs',
    });
  }
  if (typeof IAP.requestSubscription === 'function') {
    return IAP.requestSubscription({ sku, skus: [sku] });
  }
  throw new Error('expo-iap purchase API not available');
}

function purchaseOnce(IAP: any, sku: string): Promise<any> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      try { upd?.remove?.(); } catch { /* noop */ }
      try { err?.remove?.(); } catch { /* noop */ }
    };
    const upd = IAP.purchaseUpdatedListener((purchase: any) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(purchase);
    });
    const err = IAP.purchaseErrorListener((e: any) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(e);
    });
    Promise.resolve(requestSubscriptionCompat(IAP, sku)).catch((e: any) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(e);
    });
  });
}

/** Send purchase proof to the existing backend verification endpoints. */
async function verifyWithBackend(purchase: any): Promise<any> {
  if (Platform.OS === 'ios') {
    const transactionId =
      purchase?.transactionId || purchase?.id || purchase?.originalTransactionIdentifierIOS || '';
    const receiptData =
      purchase?.transactionReceipt || purchase?.jwsRepresentationIos || purchase?.purchaseToken || null;
    const res = await api.post('/iap/apple/verify', {
      transaction_id: String(transactionId),
      receipt_data: receiptData ? String(receiptData) : null,
    });
    return res.data;
  }
  const purchaseToken =
    purchase?.purchaseToken || purchase?.purchaseTokenAndroid || purchase?.dataAndroid?.purchaseToken || '';
  const productId =
    purchase?.productId || (Array.isArray(purchase?.productIds) ? purchase.productIds[0] : '') || '';
  const res = await api.post('/iap/google/verify', {
    purchase_token: String(purchaseToken),
    product_id: String(productId),
  });
  return res.data;
}

async function finishTransactionCompat(IAP: any, purchase: any): Promise<void> {
  try {
    if (typeof IAP.finishTransaction === 'function') {
      await IAP.finishTransaction({ purchase, isConsumable: false });
    }
  } catch (e) {
    console.warn('IAP finishTransaction failed (will be retried by store):', e);
  }
}

async function getAvailablePurchasesCompat(IAP: any): Promise<any[]> {
  if (typeof IAP.getAvailablePurchases === 'function') {
    return (await IAP.getAvailablePurchases()) || [];
  }
  if (typeof IAP.getAvailablePurchasesAsync === 'function') {
    return (await IAP.getAvailablePurchasesAsync()) || [];
  }
  return [];
}

/**
 * Purchase a subscription product (e.g. "com.realaicoach.basic.monthly").
 * Resolves only after the backend has verified the store receipt and applied entitlements.
 */
export async function purchaseSubscriptionNative(productId: string): Promise<IapPurchaseResult> {
  if (!productId) return { status: 'error', message: 'Missing product id' };
  if (!isNativeIapSupported()) {
    return {
      status: 'unavailable',
      reason: Platform.OS === 'web' ? 'web' : isExpoGo() ? 'expo_go' : 'module_missing',
    };
  }
  try {
    return await withConnection(async (IAP) => {
      let purchase: any;
      try {
        purchase = await purchaseOnce(IAP, productId);
      } catch (e: any) {
        if (isUserCancelledError(e)) return { status: 'cancelled' as const };
        return { status: 'error' as const, message: String(e?.message || 'Store purchase failed') };
      }

      let verification: any;
      try {
        verification = await verifyWithBackend(purchase);
      } catch (e: any) {
        // Do NOT finish the transaction if verification failed — the store will
        // redeliver it and the user can retry / use Restore Purchases.
        return {
          status: 'error' as const,
          message: String(e?.response?.data?.detail || e?.message || 'Receipt verification failed'),
        };
      }

      await finishTransactionCompat(IAP, purchase);

      return {
        status: 'success' as const,
        plan: String(verification?.plan || ''),
        active: Boolean(verification?.active),
        expiresAt: verification?.expires_at ? String(verification.expires_at) : null,
      };
    });
  } catch (e: any) {
    return { status: 'error', message: String(e?.message || 'In-app purchase failed') };
  }
}

/** Restore purchases (App Store requirement) — re-verifies every store purchase with the backend. */
export async function restorePurchasesNative(): Promise<IapRestoreResult> {
  if (!isNativeIapSupported()) {
    return {
      status: 'unavailable',
      reason: Platform.OS === 'web' ? 'web' : isExpoGo() ? 'expo_go' : 'module_missing',
    };
  }
  try {
    return await withConnection(async (IAP) => {
      const purchases = await getAvailablePurchasesCompat(IAP);
      let restoredCount = 0;
      let plan: string | null = null;
      for (const purchase of purchases) {
        try {
          const verification = await verifyWithBackend(purchase);
          if (verification?.success && verification?.active) {
            restoredCount += 1;
            plan = String(verification?.plan || plan || '');
          }
        } catch {
          // expired/invalid store entries are expected during restore; skip
        }
      }
      return { status: 'success' as const, restoredCount, plan };
    });
  } catch (e: any) {
    return { status: 'error', message: String(e?.message || 'Restore purchases failed') };
  }
}
