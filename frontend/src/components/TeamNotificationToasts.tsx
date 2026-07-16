import React, { useEffect, useState, useRef, useCallback } from 'react';
import { View, Text, Animated, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';

interface TeamToast {
  id: number;
  action: string;
  actor_name: string;
  team_name: string;
  details?: any;
  timestamp: string;
}

export default function TeamNotificationToasts() {
  const { colors } = useTheme();

  // @autofix-moved: was module-level const ACTION_META
  const ACTION_META: Record<string, { icon: string; color: string; label: string }> = {
    team_created: { icon: 'add-circle', color: colors.successText, label: 'New team created' },
    member_invited: { icon: 'person-add', color: colors.primary, label: 'joined the team' },
    member_removed: { icon: 'person-remove', color: colors.error, label: 'was removed from' },
    role_changed: { icon: 'swap-horizontal', color: colors.accent, label: 'role changed in' },
    team_updated: { icon: 'settings', color: colors.warningText, label: 'updated settings for' },
    team_deleted: { icon: 'trash', color: colors.error, label: 'deleted team' },
  };
  const { user } = useAuth();
  const { subscribeType } = useRealtime();
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _isTablet = width >= 768 && width < 1024;
  const [toasts, setToasts] = useState<TeamToast[]>([]);

  const addToast = useCallback((event: any) => {
    if (event.type !== 'team_event') return;
    const toast: TeamToast = {
      id: Date.now() + Math.random(),
      action: event.action,
      actor_name: event.actor_name || 'Someone',
      team_name: event.team_name || 'a team',
      details: event.details,
      timestamp: event.timestamp,
    };
    setToasts(prev => [toast, ...prev].slice(0, 5));
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toast.id));
    }, 6000);
  }, []);

  useEffect(() => {
    if (!user?.user_id) return;
    return subscribeType('team_event', (data) => addToast(data));
  }, [user?.user_id, addToast, subscribeType]);

  if (toasts.length === 0) return null;

  return (
    <View style={{ position: 'absolute', top: isWide ? 16 : 8, right: isWide ? 24 : 12, zIndex: 9999, gap: 8, maxWidth: 360 }} data-testid="team-notification-toasts" testID="team-notification-toasts">
      {toasts.map(toast => {
        const meta = ACTION_META[toast.action] || { icon: 'notifications', color: colors.primary, label: 'activity in' };
        return (
          <AnimatedToast key={toast.id} colors={colors} meta={meta} toast={toast} />
        );
      })}
    </View>
  );
}

function AnimatedToast({ colors, meta, toast }: { colors: any; meta: any; toast: TeamToast }) {
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const slideAnim = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, { toValue: 1, duration: 300, useNativeDriver: false }),
      Animated.timing(slideAnim, { toValue: 0, duration: 300, useNativeDriver: false }),
    ]).start();
    const timer = setTimeout(() => {
      Animated.parallel([
        Animated.timing(fadeAnim, { toValue: 0, duration: 300, useNativeDriver: false }),
        Animated.timing(slideAnim, { toValue: -20, duration: 300, useNativeDriver: false }),
      ]).start();
    }, 5500);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Animated.View style={{ opacity: fadeAnim, transform: [{ translateY: slideAnim }], backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, borderLeftWidth: 3, borderLeftColor: meta.color, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={{ width: 34, height: 34, borderRadius: 9, backgroundColor: (globalThis as any).__alphaColor(meta.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={meta.icon as any} size={16} color={meta.color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>
          {toast.actor_name} {meta.label}
        </Text>
        <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 1 }} numberOfLines={1}>{toast.team_name}</Text>
      </View>
    </Animated.View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
