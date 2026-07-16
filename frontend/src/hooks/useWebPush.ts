import { useEffect, useCallback, useRef, useState } from 'react';
import { Platform } from 'react-native';
import api from '../services/api';

const VAPID_PUBLIC_KEY = process.env.EXPO_PUBLIC_VAPID_KEY || '';

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

type PushState = 'unsupported' | 'prompt' | 'denied' | 'subscribed' | 'loading';

export function useWebPush(userId?: string) {
  const [state, setState] = useState<PushState>('loading');
  const subscribed = useRef(false);

  // Check initial state
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      setState('unsupported');
      return;
    }
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      setState('unsupported');
      return;
    }
    if (!VAPID_PUBLIC_KEY) {
      setState('unsupported');
      return;
    }

    const perm = Notification.permission;
    if (perm === 'denied') {
      setState('denied');
      return;
    }

    // Check if already subscribed
    navigator.serviceWorker.ready.then((reg) => {
      reg.pushManager.getSubscription().then((sub) => {
        if (sub) {
          setState('subscribed');
          subscribed.current = true;
          // Re-register on backend in case it was lost
          sendSubscriptionToServer(sub, userId);
        } else {
          setState(perm === 'granted' ? 'prompt' : 'prompt');
        }
      });
    }).catch(() => setState('unsupported'));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const sendSubscriptionToServer = useCallback(async (sub: PushSubscription, uid?: string) => {
    try {
      const raw = sub.toJSON();
      await api.post('/push/subscribe', {
        endpoint: raw.endpoint,
        keys: raw.keys,
        user_id: uid || null,
      });
    } catch (e) {
      console.warn('[WebPush] Failed to register subscription on server:', e);
    }
  }, []);

  const subscribe = useCallback(async () => {
    if (Platform.OS !== 'web') return false;
    try {
      setState('loading');
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setState('denied');
        return false;
      }

      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });

      await sendSubscriptionToServer(sub, userId);
      subscribed.current = true;
      setState('subscribed');
      return true;
    } catch (e) {
      console.error('[WebPush] Subscribe failed:', e);
      setState('prompt');
      return false;
    }
  }, [userId, sendSubscriptionToServer]);

  const unsubscribe = useCallback(async () => {
    if (Platform.OS !== 'web') return;
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        const raw = sub.toJSON();
        await api.post('/push/unsubscribe', {
          endpoint: raw.endpoint,
          keys: raw.keys,
        });
        await sub.unsubscribe();
      }
      subscribed.current = false;
      setState('prompt');
    } catch (e) {
      console.warn('[WebPush] Unsubscribe failed:', e);
    }
  }, []);

  return { state, subscribe, unsubscribe };
}
