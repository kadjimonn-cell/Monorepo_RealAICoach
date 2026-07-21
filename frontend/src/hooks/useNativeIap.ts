import { useCallback, useMemo, useState } from 'react';
import {
  isNativeIapSupported,
  purchaseSubscriptionNative,
  restorePurchasesNative,
  IapPurchaseResult,
  IapRestoreResult,
} from '../services/nativeIap';

/**
 * Phase 3 — React hook around the native IAP service.
 * `supported` is false on web and in Expo Go, so all consuming UI stays
 * byte-identical on web (native-only rendering paths).
 */
export function useNativeIap() {
  const supported = useMemo(() => isNativeIapSupported(), []);
  const [busy, setBusy] = useState(false);

  const purchase = useCallback(async (productId: string): Promise<IapPurchaseResult> => {
    if (busy) return { status: 'error', message: 'Another purchase is in progress' };
    setBusy(true);
    try {
      return await purchaseSubscriptionNative(productId);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const restore = useCallback(async (): Promise<IapRestoreResult> => {
    if (busy) return { status: 'error', message: 'Another store operation is in progress' };
    setBusy(true);
    try {
      return await restorePurchasesNative();
    } finally {
      setBusy(false);
    }
  }, [busy]);

  return { supported, busy, purchase, restore };
}
