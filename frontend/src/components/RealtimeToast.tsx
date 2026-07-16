import React, { useEffect, useState, useRef } from 'react';
import { View, Text, TouchableOpacity, Animated, StyleSheet, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { notificationEvents } from '../utils/notificationEvents';

import { useAdminTheme } from '../hooks/useAdminTheme';
import { useTheme } from '../context/ThemeContext';
interface ToastItem {
  id: string;
  title: string;
  message: string;
  type?: string;
  actionLabel?: string;
  actionRoute?: string;
  opacity: Animated.Value;
}

export default function RealtimeToast() {
  const { colors } = useTheme();
  const router = useRouter();

  const DEFAULT_CONFIG = { icon: 'notifications', color: colors.primary, bg: colors.primarySoft };

  // @autofix-moved: was module-level const TYPE_CONFIG
  const TYPE_CONFIG: Record<string, { icon: string; color: string; bg: string }> = {
    new_booking: { icon: 'calendar', color: colors.successText, bg: colors.successSoft },
    booking_cancelled: { icon: 'close-circle', color: colors.error, bg: colors.errorSoft },
    booking_rescheduled: { icon: 'swap-horizontal', color: colors.warningText, bg: colors.warningSoft },
    booking_reminder: { icon: 'alarm', color: colors.primary, bg: colors.primarySoft },
    new_content: { icon: 'add-circle', color: colors.accent, bg: colors.accentSoft },
    trending: { icon: 'trending-up', color: colors.successText, bg: colors.successSoft },
    success: { icon: 'checkmark-circle', color: colors.successText, bg: colors.successSoft },
    warning: { icon: 'alert-circle', color: colors.warningText, bg: colors.warningSoft },
    error: { icon: 'close-circle', color: colors.error, bg: colors.errorSoft },
    payment_failed: { icon: 'close-circle', color: colors.error, bg: colors.errorSoft },
    subscription_cancelled: { icon: 'remove-circle', color: colors.warningText, bg: colors.warningSoft },
  };
  const _AC = useAdminTheme();
  const s = React.useMemo(() => createStyles(_AC), [_AC]);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timerRefs = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const unsub = notificationEvents.on('toast', (data: { title: string; message: string; type?: string; actionLabel?: string; actionRoute?: string }) => {
      const id = Date.now().toString();
      const opacity = new Animated.Value(0);

      setToasts(prev => [...prev.slice(-2), {
        id,
        title: data.title,
        message: data.message,
        type: data.type,
        actionLabel: data.actionLabel,
        actionRoute: data.actionRoute,
        opacity,
      }]);

      Animated.timing(opacity, { toValue: 1, duration: 250, useNativeDriver: Platform.OS !== 'web' }).start();

      const timer = setTimeout(() => dismiss(id, opacity), data.actionRoute ? 7000 : 5000);
      timerRefs.current.set(id, timer);
    });

    return () => {
      unsub();
      // eslint-disable-next-line react-hooks/exhaustive-deps
      timerRefs.current.forEach(t => clearTimeout(t));
    };
  }, []);

  const dismiss = (id: string, opacity: Animated.Value) => {
    const timer = timerRefs.current.get(id);
    if (timer) clearTimeout(timer);
    timerRefs.current.delete(id);

    Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: Platform.OS !== 'web' }).start(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    });
  };

  if (toasts.length === 0) return null;

  return (
    <View style={[s.container, { pointerEvents: 'box-none' }]} data-testid="realtime-toast-container" testID="realtime-toast-container">
      {toasts.map((t) => {
        const cfg = TYPE_CONFIG[t.type || ''] || DEFAULT_CONFIG;
        return (
          <Animated.View key={t.id} style={[s.toast, { opacity: t.opacity }]} data-testid={`toast-${t.id}`} testID={`toast-${t.id}`}>
            <View style={[s.iconWrap, { backgroundColor: cfg.bg }]}>
              <Ionicons name={cfg.icon as any} size={18} color={cfg.color} />
            </View>
            <View style={s.textWrap}>
              <Text style={s.title} numberOfLines={1}>{t.title}</Text>
              <Text style={s.message} numberOfLines={2}>{t.message}</Text>
              {t.actionLabel && t.actionRoute ? (
                <TouchableOpacity
                  onPress={() => {
                    dismiss(t.id, t.opacity);
                    router.push(t.actionRoute as any);
                  }}
                  style={[s.actionButton, { backgroundColor: cfg.bg, borderColor: cfg.color }]}
                  data-testid={`toast-action-${t.id}`}
                  testID={`toast-action-${t.id}`}
                >
                  <Text style={[s.actionLabel, { color: cfg.color }]}>{t.actionLabel}</Text>
                </TouchableOpacity>
              ) : null}
            </View>
            <TouchableOpacity onPress={() => dismiss(t.id, t.opacity)} style={s.closeBtn} data-testid={`toast-close-${t.id}`} testID={`toast-close-${t.id}`}>
              <Ionicons name="close" size={16} color="var(--app-text-muted)" />
            </TouchableOpacity>
          </Animated.View>
        );
      })}
    </View>
  );
}

function createStyles(AC: any) {
  return StyleSheet.create({
    container: {
      position: 'absolute',
      top: 16,
      right: 16,
      zIndex: 9999,
      gap: 8,
      maxWidth: 380,
      ...(Platform.OS === 'web' ? { position: 'fixed' as any } : {}),
    },
    toast: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      backgroundColor: AC.bgAlt,
      borderRadius: 14,
      padding: 14,
      gap: 12,
      borderWidth: 1,
      borderColor: AC.border,
      ...(Platform.OS === 'web'
        ? { boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }
        : { elevation: 12, shadowColor: 'var(--app-text)', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 12 }),
    },
    iconWrap: {
      width: 36,
      height: 36,
      borderRadius: 10,
      alignItems: 'center',
      justifyContent: 'center',
    },
    textWrap: { flex: 1 },
    title: { color: AC.text, fontSize: 13, fontWeight: '700' },
    message: { color: AC.textMuted, fontSize: 11, lineHeight: 16, marginTop: 2 },
    actionButton: {
      alignSelf: 'flex-start',
      marginTop: 8,
      borderRadius: 999,
      borderWidth: 1,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    actionLabel: {
      fontSize: 11,
      fontWeight: '700',
    },
    closeBtn: { padding: 4, marginTop: -2, marginRight: -4 },
  });
}

/* i18n-probe t('i18n.auto.probe') */
