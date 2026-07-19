import { useEffect, useRef, useCallback } from 'react';
import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { router } from 'expo-router';
import api from '../services/api';
import { clientLogger } from '../utils/clientLogger';

// Only import expo-notifications on native platforms
let Notifications: any = null;
let Device: any = null;

if (Platform.OS !== 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Notifications = require('expo-notifications');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  Device = require('expo-device');

  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: true,
    }),
  });
}

export function usePushNotifications(userId?: string) {
  const notificationListener = useRef<any>();
  const responseListener = useRef<any>();

  const registerForPush = useCallback(async () => {
    if (Platform.OS === 'web' || !Notifications || !Device) return null;
    if (!Device.isDevice) return null;

    // Expo Go (SDK 53+) does not support remote push tokens — no-op gracefully.
    const isExpoGo =
      (Constants as any)?.executionEnvironment === 'storeClient' ||
      (Constants as any)?.appOwnership === 'expo';
    if (isExpoGo) {
      clientLogger.log('Push registration skipped: remote push requires a development/production build (Expo Go limitation).');
      return null;
    }

    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Default',
        importance: Notifications.AndroidImportance.DEFAULT,
        vibrationPattern: [0, 250, 250, 250],
      });
    }

    const { status: existing } = await Notifications.getPermissionsAsync();
    let finalStatus = existing;

    if (existing !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }

    if (finalStatus !== 'granted') return null;

    let token: string | null = null;
    try {
      const projectId =
        Constants?.expoConfig?.extra?.eas?.projectId ?? (Constants as any)?.easConfig?.projectId;
      const tokenData = await Notifications.getExpoPushTokenAsync(
        projectId ? { projectId } : undefined
      );
      token = tokenData.data;
    } catch (e) {
      clientLogger.log('Expo push token unavailable on this device/build:', e);
      return null;
    }

    try {
      await api.post('/notifications/push-token', { push_token: token });
    } catch (e) {
      console.warn('Failed to register push token:', e);
    }

    return token;
  }, []);

  useEffect(() => {
    if (!userId || Platform.OS === 'web' || !Notifications) return;

    registerForPush();

    notificationListener.current = Notifications.addNotificationReceivedListener((notification: any) => {
      clientLogger.log('Notification received:', notification.request.content.title);
    });

    responseListener.current = Notifications.addNotificationResponseReceivedListener((response: any) => {
      const data = response.notification.request.content.data;
      clientLogger.log('Notification tapped:', data);
      const url = data?.action_url;
      if (url && typeof url === 'string' && url.startsWith('/')) {
        try {
          router.push(url as any);
        } catch (e) {
          clientLogger.log('Notification deep-link failed:', e);
        }
      }
    });

    return () => {
      if (notificationListener.current) {
        notificationListener.current.remove();
      }
      if (responseListener.current) {
        responseListener.current.remove();
      }
    };
  }, [userId, registerForPush]);

  return { registerForPush };
}
