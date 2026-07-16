import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { notificationEvents } from '../utils/notificationEvents';

interface Toast {
  id: string;
  title: string;
  message: string;
  type?: string;
}

/**
 * InAppToastOverlay — Shows floating toast notifications from real-time events.
 * Renders at the top of the screen, auto-dismisses after 5 seconds.
 * Must be placed in the root layout or AppShell.
 */
export default function InAppToastOverlay() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const { theme , colors} = useTheme();
  const T = theme === 'dark'
    ? { bg: colors.card, border: colors.border, text: colors.text, accent: colors.info }
    : { bg: colors.card, border: colors.border, text: colors.text, accent: colors.info };

  useEffect(() => {
    const unsub = notificationEvents.on('toast', (data: any) => {
      const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
      const toast: Toast = {
        id,
        title: data.title || 'Notification',
        message: data.message || '',
        type: data.type || 'info',
      };
      setToasts(prev => [toast, ...prev].slice(0, 3));
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id));
      }, 5000);
    });
    return unsub;
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  if (toasts.length === 0) return null;

  const iconMap: Record<string, string> = {
    success: 'checkmark-circle',
    error: 'alert-circle',
    warning: 'warning',
    security: 'shield-checkmark',
    achievement: 'trophy',
    info: 'information-circle',
  };

  return (
    <View style={[styles.container]} data-testid="toast-overlay" testID="toast-overlay">
      {toasts.map((toast) => {
        const icon = iconMap[toast.type || 'info'] || 'information-circle';
        return (
          <View key={toast.id} style={[styles.toast, { backgroundColor: T.bg, borderColor: T.border }]} data-testid={`toast-${toast.id}`} testID={`toast-${toast.id}`}>
            <Ionicons name={icon as any} size={20} color={T.accent} style={{ marginRight: 10 }} />
            <View style={{ flex: 1 }}>
              <Text style={[styles.title, { color: T.text }]}>{toast.title}</Text>
              {toast.message ? <Text style={[styles.message, { color: T.text, opacity: 0.7 }]} numberOfLines={2}>{toast.message}</Text> : null}
            </View>
            <TouchableOpacity onPress={() => dismiss(toast.id)} data-testid={`toast-dismiss-${toast.id}`} testID={`toast-dismiss-${toast.id}`}>
              <Ionicons name="close" size={18} color={T.text} />
            </TouchableOpacity>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 16,
    right: 16,
    zIndex: 9999,
    maxWidth: 380,
  },
  toast: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: 8,
    shadowColor: 'var(--app-text)',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 12,
    elevation: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '600',
  },
  message: {
    fontSize: 12,
    marginTop: 2,
  },
});

/* i18n-probe t('i18n.auto.probe') */
