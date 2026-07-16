import React, { useEffect, useState, useCallback, createContext, useContext, useRef } from 'react';
import { View, Text, TouchableOpacity, ScrollView, ActivityIndicator, Platform, useWindowDimensions, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useRealtime } from '../context/RealtimeContext';
import api from '../services/api';
import { notificationEvents } from '../utils/notificationEvents';
import { useLiveQuery } from '../hooks/useLiveQuery';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

type NotificationScope = 'user' | 'admin';

type UserNotification = {
  notification_id: string;
  title: string;
  message: string;
  type: string;
  action_url?: string;
  created_at: string;
  read?: boolean;
};

type AdminNotification = {
  id: string;
  type: string;
  severity?: string;
  title: string;
  message: string;
  timestamp: string;
  read?: boolean;
};

type NotificationCounts = {
  total: number;
  security: number;
  signups: number;
  payment_failures: number;
  expiring: number;
  system: number;
};

export const NOTIFICATION_BELL_SNAPSHOT = {
  width: 40,
  height: 40,
  borderRadius: 20,
  iconSize: 22,
};

const EMPTY_COUNTS: NotificationCounts = {
  total: 0,
  security: 0,
  signups: 0,
  payment_failures: 0,
  expiring: 0,
  system: 0,
};

type IconColorKey = 'primary' | 'accent' | 'success' | 'warning' | 'error' | 'textMuted';
const TYPE_ICON: Record<string, { name: string; colorKey: IconColorKey }> = {
  new_content: { name: 'add-circle', colorKey: 'accent' },
  expiring_soon: { name: 'time', colorKey: 'warning' },
  trending: { name: 'trending-up', colorKey: 'success' },
  new_booking: { name: 'calendar', colorKey: 'success' },
  booking_cancelled: { name: 'close-circle', colorKey: 'error' },
  booking_rescheduled: { name: 'swap-horizontal', colorKey: 'warning' },
  booking_reminder: { name: 'alarm', colorKey: 'primary' },
  agenda_reminder: { name: 'alarm', colorKey: 'primary' },
  team_invite: { name: 'people', colorKey: 'accent' },
  team_event: { name: 'people-circle', colorKey: 'primary' },
  payment: { name: 'card', colorKey: 'success' },
  security: { name: 'shield', colorKey: 'error' },
  security_alert: { name: 'shield-half', colorKey: 'error' },
  security_tip: { name: 'key', colorKey: 'warning' },
  signup: { name: 'person-add', colorKey: 'primary' },
  payment_failure: { name: 'card', colorKey: 'warning' },
  payment_setup: { name: 'wallet', colorKey: 'success' },
  subscription_expiry: { name: 'time', colorKey: 'accent' },
  subscription_renewal: { name: 'refresh', colorKey: 'success' },
  subscription_expired: { name: 'close-circle', colorKey: 'error' },
  upgrade_suggestion: { name: 'sparkles', colorKey: 'accent' },
  daily_briefing: { name: 'sunny', colorKey: 'warning' },
  streak_reminder: { name: 'flame', colorKey: 'warning' },
  inactivity_reminder: { name: 'notifications-off', colorKey: 'textMuted' },
  app_discovery: { name: 'rocket', colorKey: 'primary' },
  system: { name: 'settings', colorKey: 'textMuted' },
  general: { name: 'notifications', colorKey: 'primary' },
  referral_signup: { name: 'person-add', colorKey: 'success' },
  referral_subscription: { name: 'cash', colorKey: 'warning' },
  referral_credit_applied: { name: 'wallet', colorKey: 'accent' },
};

const NotifCtx = createContext<any>({
  open: false,
  setOpen: () => {},
  unread: 0,
  counts: EMPTY_COUNTS,
  notifs: [],
  loading: false,
  scope: 'user' as NotificationScope,
  openDropdown: () => {},
  markRead: () => {},
  markAllRead: () => {},
  refreshNotifications: async () => {},
});

export const useNotifications = () => useContext(NotifCtx);
export const useNotificationCenter = () => useContext(NotifCtx);

function timeAgo(dateStr?: string) {
  if (!dateStr) return 'now';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function NotificationProvider({ children, scope = 'user' }: { children: React.ReactNode; scope?: NotificationScope }) {
  const { user } = useAuth();
  const { subscribeType } = useRealtime();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [counts, setCounts] = useState<NotificationCounts>(EMPTY_COUNTS);
  const [notifs, setNotifs] = useState<(UserNotification | AdminNotification)[]>([]);
  const [loading, setLoading] = useState(false);
  const isAdminScope = scope === 'admin';
  const adminEnabled = Boolean(isAdminScope && user?.is_admin);
  const { data: liveUserNotifications } = useLiveQuery(
    !isAdminScope && user?.user_id ? `/notifications/${user.user_id}` : '',
    { entity: 'notifications', pollInterval: 60000, deps: [user?.user_id, isAdminScope] }
  );

  const applyUserNotifications = useCallback((items: UserNotification[], nextUnread?: number) => {
    const unreadCount = typeof nextUnread === 'number' ? nextUnread : items.filter((item) => !item.read).length;
    setNotifs(items);
    setUnread(unreadCount);
    setCounts({ ...EMPTY_COUNTS, total: unreadCount });
  }, []);

  const applyAdminNotifications = useCallback((items: AdminNotification[], nextCounts?: Partial<NotificationCounts>) => {
    const mergedCounts = { ...EMPTY_COUNTS, ...(nextCounts || {}) };
    setNotifs(items);
    setCounts(mergedCounts);
    setUnread(mergedCounts.total || 0);
  }, []);

  const refreshUserNotifications = useCallback(async (limit = 10) => {
    if (!user?.user_id) {
      applyUserNotifications([], 0);
      return;
    }
    const { data } = await api.get(`/notifications/${user.user_id}?limit=${limit}`);
    applyUserNotifications(data.notifications || [], data.unread_count || 0);
  }, [applyUserNotifications, user?.user_id]);

  const refreshAdminNotifications = useCallback(async (limit = 15) => {
    if (!adminEnabled) {
      applyAdminNotifications([], EMPTY_COUNTS);
      return;
    }
    const { data } = await api.get(`/admin/notifications/live?limit=${limit}`);
    applyAdminNotifications(data.notifications || [], data.counts || EMPTY_COUNTS);
  }, [adminEnabled, applyAdminNotifications]);

  const refreshNotifications = useCallback(async () => {
    if (isAdminScope) {
      await refreshAdminNotifications();
      return;
    }
    await refreshUserNotifications();
  }, [isAdminScope, refreshAdminNotifications, refreshUserNotifications]);

  useEffect(() => {
    if (isAdminScope || !liveUserNotifications?.notifications) return;
    applyUserNotifications(
      liveUserNotifications.notifications || [],
      (liveUserNotifications.notifications || []).filter((item: UserNotification) => !item.read).length,
    );
  }, [applyUserNotifications, isAdminScope, liveUserNotifications]);

  useEffect(() => {
    if (isAdminScope) return;
    const unsub = notificationEvents.on('unread_update', (data: any) => {
      if (typeof data.unread_count === 'number') {
        setUnread(data.unread_count);
        setCounts((prev: NotificationCounts) => ({ ...prev, total: data.unread_count || 0 }));
      }
      if (data.notification) {
        setNotifs((prev: UserNotification[]) => [data.notification, ...prev].slice(0, 10));
      }
    });
    return unsub;
  }, [isAdminScope]);

  useEffect(() => {
    if (isAdminScope || !user?.user_id) return;

    const unsubNotification = subscribeType('notification', (msg: any) => {
      if (!msg?.notification) return;
      setNotifs((prev: UserNotification[]) => [msg.notification, ...prev].slice(0, 15));
      if (typeof msg.unread_count === 'number') {
        setUnread(msg.unread_count);
        setCounts((prev: NotificationCounts) => ({ ...prev, total: msg.unread_count || 0 }));
      } else {
        setUnread((prev) => prev + 1);
        setCounts((prev: NotificationCounts) => ({ ...prev, total: (prev.total || 0) + 1 }));
      }
      notificationEvents.emit('unread_update', {
        unread_count: msg.unread_count,
        notification: msg.notification,
      });
    });

    const unsubSubscription = subscribeType('subscription_update', (msg: any) => {
      notificationEvents.emit('subscription_update', msg);
    });

    return () => {
      unsubNotification();
      unsubSubscription();
    };
  }, [isAdminScope, subscribeType, user?.user_id]);

  useEffect(() => {
    if (!adminEnabled) return;
    void refreshAdminNotifications();
  }, [adminEnabled, refreshAdminNotifications]);

  useEffect(() => {
    if (!adminEnabled) return;
    const unsubNotification = subscribeType('notification', () => refreshAdminNotifications());
    const unsubSubscription = subscribeType('subscription_update', () => refreshAdminNotifications());
    return () => {
      unsubNotification();
      unsubSubscription();
    };
  }, [adminEnabled, refreshAdminNotifications, subscribeType]);

  useEffect(() => {
    if (user?.user_id) return;
    setOpen(false);
    setUnread(0);
    setCounts(EMPTY_COUNTS);
    setNotifs([]);
    setLoading(false);
  }, [user?.user_id]);

  const openDropdown = async () => {
    const hasIdentity = Boolean(user?.user_id || user?.email);
    if (!hasIdentity && !isAdminScope) {
      setOpen(false);
      setLoading(false);
      setNotifs([]);
      setCounts(EMPTY_COUNTS);
      return;
    }

    setOpen(true);
    setLoading(true);
    try {
      await refreshNotifications();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/NotificationBell.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setLoading(false);
  };

  const markRead = async (id: string) => {
    if (isAdminScope) return;
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifs((prev: UserNotification[]) => prev.map((item) => item.notification_id === id ? { ...item, read: true } : item));
      setUnread((prev) => Math.max(0, prev - 1));
      setCounts((prev: NotificationCounts) => ({ ...prev, total: Math.max(0, (prev.total || 0) - 1) }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/NotificationBell.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  const markAllRead = async () => {
    if (isAdminScope) return;
    try {
      await api.post(`/notifications/${user?.user_id || 'me'}/read-all`);
      setNotifs((prev: UserNotification[]) => prev.map((item) => ({ ...item, read: true })));
      setUnread(0);
      setCounts((prev: NotificationCounts) => ({ ...prev, total: 0 }));
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/NotificationBell.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  };

  return (
    <NotifCtx.Provider value={{ open, setOpen, unread, counts, notifs, loading, scope, openDropdown, markRead, markAllRead, refreshNotifications }}>
      {children}
    </NotifCtx.Provider>
  );
}

export default function NotificationBell() {
  const { colors } = useTheme();
  const { open, setOpen, unread, counts, openDropdown, scope } = useContext(NotifCtx);
  const visibleCount = scope === 'admin' ? counts.total || 0 : unread;
  const lastToggleRef = useRef(0);

  const handlePress = useCallback(() => {
    const now = Date.now();
    if (now - lastToggleRef.current < 300) {
      return;
    }
    lastToggleRef.current = now;

    if (open) {
      setOpen(false);
      return;
    }
    openDropdown();
    notificationEvents.emit('open-notifications');
  }, [open, openDropdown, setOpen]);

  const bellContent = (
    <>
      <Ionicons name={open ? 'notifications' : 'notifications-outline'} size={NOTIFICATION_BELL_SNAPSHOT.iconSize} color={open ? colors.primary : colors.textSec} />
      {visibleCount > 0 && (
        <View
          data-testid={scope === 'admin' ? 'admin-notification-bell-unread-count' : 'notification-bell-unread-count'} testID={scope === 'admin' ? 'admin-notification-bell-unread-count' : 'notification-bell-unread-count'}
          style={{ position: 'absolute', top: 0, right: 0, backgroundColor: colors.error, borderRadius: 10, minWidth: 18, height: 18, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4, borderWidth: 2, borderColor: colors.bg }}
        >
          <Text style={{ color: colors.primaryText, fontSize: 9, fontWeight: '800' }}>{visibleCount > 9 ? '9+' : visibleCount}</Text>
        </View>
      )}
    </>
  );

  // On web: render a native <div> with onClick — immune to Expo's mount/unmount cycles
  if (Platform.OS === 'web') {
    return React.createElement('div', {
      onClick: (e: any) => { e.stopPropagation(); handlePress(); },
      'data-testid': scope === 'admin' ? 'admin-notification-bell' : 'notification-bell',
      role: 'button',
      'aria-label': scope === 'admin' ? 'Admin notifications' : 'Notifications',
      style: {
        width: NOTIFICATION_BELL_SNAPSHOT.width,
        height: NOTIFICATION_BELL_SNAPSHOT.height,
        borderRadius: NOTIFICATION_BELL_SNAPSHOT.borderRadius,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative', cursor: 'pointer',
      },
    }, bellContent);
  }

  // Native: use TouchableOpacity
  return (
    <TouchableOpacity
      onPress={handlePress}
      accessibilityRole="button"
      accessibilityLabel={scope === 'admin' ? 'Admin notifications' : 'Notifications'}
      style={{ width: NOTIFICATION_BELL_SNAPSHOT.width, height: NOTIFICATION_BELL_SNAPSHOT.height, borderRadius: NOTIFICATION_BELL_SNAPSHOT.borderRadius, alignItems: 'center', justifyContent: 'center', position: 'relative' }}
      data-testid={scope === 'admin' ? 'admin-notification-bell' : 'notification-bell'} testID={scope === 'admin' ? 'admin-notification-bell' : 'notification-bell'}
    >
      {bellContent}
    </TouchableOpacity>
  );
}

function UserNotificationOverlay() {
  const { colors } = useTheme();
  const router = useRouter();
  const { width: screenWidth } = useWindowDimensions();
  const isMobile = screenWidth < 768;
  const { open, setOpen, unread, notifs, loading, markRead, markAllRead } = useContext(NotifCtx);
  const openedAtRef = useRef(0);

  useEffect(() => {
    if (open) openedAtRef.current = Date.now();
  }, [open]);

  if (!open) return null;

  const dropdownWidth = isMobile ? screenWidth - 32 : 380;
  const close = () => {
    if (Date.now() - openedAtRef.current < 1200) return;
    setOpen(false);
  };

  return (
    <>
      <Pressable
        accessibilityLabel="Notification backdrop button"
        style={[
          {
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: colors.overlay,
            zIndex: 99998,
          },
          Platform.OS === 'web' ? { position: 'fixed' as any, top: 0, left: 0, width: '100vw', height: '100vh' } as any : {},
        ]}
        onPress={close}
        data-testid="notification-backdrop" testID="notification-backdrop"
      />

      <View
        style={[
          {
            position: 'absolute',
            top: isMobile ? 56 : 12,
            right: isMobile ? 16 : undefined,
            left: isMobile ? 16 : 268,
            width: dropdownWidth,
            maxHeight: isMobile ? (screenWidth > 400 ? 520 : 440) : 520,
            borderRadius: 16,
            backgroundColor: colors.card,
            borderWidth: 1,
            borderColor: colors.border,
            overflow: 'hidden',
            zIndex: 99999,
          },
          Platform.OS === 'web' ? { position: 'fixed' as any, boxShadow: '0 12px 48px rgba(0,0,0,0.4)' } as any : {},
        ]}
        data-testid="notification-dropdown" testID="notification-dropdown"
      >
        <View style={{ paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          {isMobile ? (
            <>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                  <Ionicons name="notifications" size={18} color={colors.primary} />
                  <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text, flexShrink: 1 }} numberOfLines={1}>Notifications</Text>
                  {unread > 0 && (
                    <View style={{ backgroundColor: colors.primary, borderRadius: 10, minWidth: 20, height: 20, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 }}>
                      <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{unread}</Text>
                    </View>
                  )}
                </View>
                <TouchableOpacity onPress={close} style={{ padding: 4, marginLeft: 10 }} data-testid="close-notifications-btn" testID="close-notifications-btn">
                  <Ionicons name="close" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                {unread > 0 && (
                  <TouchableOpacity onPress={markAllRead} data-testid="mark-all-read-btn" testID="mark-all-read-btn" style={{ paddingVertical: 4, paddingHorizontal: 8 }}>
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>Mark all read</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => { close(); router.push('/notifications'); }} data-testid="view-all-notifications-btn" testID="view-all-notifications-btn" style={{ paddingVertical: 4, paddingHorizontal: 8 }}>
                  <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>View all</Text>
                </TouchableOpacity>
              </View>
            </>
          ) : (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                <Ionicons name="notifications" size={18} color={colors.primary} />
                <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text, flexShrink: 1 }} numberOfLines={1}>Notifications</Text>
                {unread > 0 && (
                  <View style={{ backgroundColor: colors.primary, borderRadius: 10, minWidth: 20, height: 20, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 }}>
                    <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{unread}</Text>
                  </View>
                )}
              </View>
              <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center', flexShrink: 0 }}>
                {unread > 0 && (
                  <TouchableOpacity onPress={markAllRead} data-testid="mark-all-read-btn" testID="mark-all-read-btn" style={{ paddingVertical: 4, paddingHorizontal: 8 }}>
                    <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>Mark all read</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity onPress={() => { close(); router.push('/notifications'); }} data-testid="view-all-notifications-btn" testID="view-all-notifications-btn" style={{ paddingVertical: 4, paddingHorizontal: 8 }}>
                  <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>View all</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={close} style={{ padding: 4 }} data-testid="close-notifications-btn" testID="close-notifications-btn">
                  <Ionicons name="close" size={18} color={colors.textMuted} />
                </TouchableOpacity>
              </View>
            </View>
          )}
        </View>

        {loading ? (
          <ActivityIndicator style={{ padding: 32 }} color={colors.primary} />
        ) : notifs.length === 0 ? (
          <View style={{ padding: 40, alignItems: 'center' }}>
            <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '10'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
              <Ionicons name="notifications-off-outline" size={28} color={colors.textMuted} />
            </View>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>All caught up</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>No new notifications</Text>
          </View>
        ) : (
          <ScrollView style={{ maxHeight: 380 }} showsVerticalScrollIndicator={false}>
            {(notifs as UserNotification[]).map((item) => {
              const iconDef = TYPE_ICON[item.type] || { name: 'notifications', colorKey: 'primary' as IconColorKey };
              const iconColor = colors[iconDef.colorKey] || colors.primary;
              return (
                <TouchableOpacity
                  key={item.notification_id || item.title}
                  style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 12, paddingHorizontal: 16, backgroundColor: (globalThis as any).__alphaColor(item.read ? 'transparent' : colors.primary, '06'), borderBottomWidth: 1, borderBottomColor: colors.border }}
                  onPress={() => markRead(item.notification_id)}
                  data-testid={`notif-item-${item.notification_id}`} testID={`notif-item-${item.notification_id}`}
                >
                  <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(iconColor, '12'), alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Ionicons name={iconDef.name as any} size={16} color={iconColor} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }} numberOfLines={1}>{item.title}</Text>
                    <Text style={{ fontSize: 12, color: colors.textSec, lineHeight: 17, marginTop: 2 }} numberOfLines={2}>{item.message}</Text>
                    <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4, fontWeight: '500' }}>{timeAgo(item.created_at)}</Text>
                  </View>
                  {!item.read && <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary, marginTop: 4, flexShrink: 0 }} />}
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        )}
      </View>
    </>
  );
}

function AdminNotificationOverlay() {
  const { colors } = useTheme();
  const router = useRouter();
  const { width: screenWidth } = useWindowDimensions();
  const isMobile = screenWidth < 768;
  const { open, setOpen, counts, notifs, loading } = useContext(NotifCtx);
  const openedAtRef = useRef(0);

  useEffect(() => {
    if (open) openedAtRef.current = Date.now();
  }, [open]);

  if (!open) return null;

  const dropdownWidth = isMobile ? screenWidth - 32 : 400;
  const close = () => {
    if (Date.now() - openedAtRef.current < 1200) return;
    setOpen(false);
  };
  const chips = [
    { key: 'security', icon: 'shield', color: colors.error, value: counts.security },
    { key: 'signups', icon: 'person-add', color: colors.primary, value: counts.signups },
    { key: 'payment-failures', icon: 'card', color: colors.warningText, value: counts.payment_failures },
    { key: 'expiring', icon: 'time', color: colors.purpleText, value: counts.expiring },
    { key: 'system', icon: 'settings', color: colors.successText, value: counts.system },
  ].filter((item) => item.value > 0);

  return (
    <>
      <Pressable
        accessibilityLabel="Admin notification backdrop button"
        style={[
          {
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: colors.overlay,
            zIndex: 99998,
          },
          Platform.OS === 'web' ? { position: 'fixed' as any, top: 0, left: 0, width: '100vw', height: '100vh' } as any : {},
        ]}
        onPress={close}
        data-testid="admin-notification-backdrop" testID="admin-notification-backdrop"
      />

      <View
        style={[
          {
            position: 'absolute',
            top: isMobile ? 56 : 12,
            right: isMobile ? 16 : undefined,
            left: isMobile ? 16 : 268,
            width: dropdownWidth,
            maxHeight: isMobile ? (screenWidth > 400 ? 560 : 480) : 560,
            borderRadius: 16,
            backgroundColor: colors.card,
            borderWidth: 1,
            borderColor: colors.border,
            overflow: 'hidden',
            zIndex: 99999,
          },
          Platform.OS === 'web' ? { position: 'fixed' as any, boxShadow: '0 12px 48px rgba(0,0,0,0.4)' } as any : {},
        ]}
        data-testid="admin-notification-dropdown" testID="admin-notification-dropdown"
      >
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
            <Ionicons name="notifications" size={18} color={colors.primary} />
            <Text style={{ fontSize: 16, fontWeight: '800', color: colors.text }}>Operations Alerts</Text>
            {counts.total > 0 && (
              <View style={{ backgroundColor: colors.primary, borderRadius: 10, minWidth: 20, height: 20, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 }}>
                <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{counts.total}</Text>
              </View>
            )}
          </View>
          <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
            <TouchableOpacity onPress={() => { close(); router.push('/executive-dashboard?section=notifications' as any); }} data-testid="admin-open-notification-center-btn" testID="admin-open-notification-center-btn" style={{ paddingVertical: 4, paddingHorizontal: 8 }}>
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>Manage</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={close} style={{ padding: 4 }} data-testid="admin-close-notifications-btn" testID="admin-close-notifications-btn">
              <Ionicons name="close" size={18} color={colors.textMuted} />
            </TouchableOpacity>
          </View>
        </View>

        {chips.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 16, paddingVertical: 10, gap: 8 }}>
            {chips.map((chip) => (
              <View key={chip.key} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: (globalThis as any).__alphaColor(chip.color, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(chip.color, '24') }} data-testid={`admin-notification-chip-${chip.key}`} testID={`admin-notification-chip-${chip.key}`}>
                <Ionicons name={chip.icon as any} size={12} color={chip.color} />
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '700' }}>{chip.value}</Text>
              </View>
            ))}
          </ScrollView>
        )}

        {loading ? (
          <ActivityIndicator style={{ padding: 32 }} color={colors.primary} />
        ) : notifs.length === 0 ? (
          <View style={{ padding: 40, alignItems: 'center' }}>
            <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '10'), alignItems: 'center', justifyContent: 'center', marginBottom: 12 }}>
              <Ionicons name="checkmark-circle-outline" size={28} color={colors.successText} />
            </View>
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700' }}>All clear</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 4 }}>No live admin alerts need attention right now.</Text>
          </View>
        ) : (
          <ScrollView style={{ maxHeight: 400 }} showsVerticalScrollIndicator={false}>
            {(notifs as AdminNotification[]).map((item, idx) => {
              const iconDef = TYPE_ICON[item.type] || TYPE_ICON.general;
              const iconColor = colors[iconDef.colorKey] || colors.primary;
              const tone = item.severity === 'critical' ? colors.error : item.severity === 'warning' ? colors.warning : iconColor;
              return (
                <View
                  key={item.id || idx}
                  style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 12, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: colors.border }}
                  data-testid={`admin-notif-item-${item.id || idx}`} testID={`admin-notif-item-${item.id || idx}`}
                >
                  <View style={{ width: 36, height: 36, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(tone, '12'), alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Ionicons name={iconDef.name as any} size={16} color={tone} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={{ fontSize: 13, fontWeight: '700', color: colors.text }} numberOfLines={1}>{item.title}</Text>
                    <Text style={{ fontSize: 12, color: colors.textSec, lineHeight: 17, marginTop: 2 }} numberOfLines={2}>{item.message}</Text>
                    <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4, fontWeight: '500' }}>{timeAgo(item.timestamp)}</Text>
                  </View>
                </View>
              );
            })}
          </ScrollView>
        )}

        <View style={{ flexDirection: 'row', gap: 10, paddingHorizontal: 16, paddingVertical: 14, borderTopWidth: 1, borderTopColor: colors.border }}>
          <TouchableOpacity onPress={() => { close(); router.push('/executive-dashboard?section=notifications' as any); }} data-testid="admin-notification-manage-button" testID="admin-notification-manage-button" style={{ flex: 1, borderRadius: 12, borderWidth: 1, borderColor: colors.border, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.bgSoft }}>
            <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }}>Open Management</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { close(); router.push('/admin-activity-log' as any); }} data-testid="admin-notification-activity-log-button" testID="admin-notification-activity-log-button" style={{ flex: 1, borderRadius: 12, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }}>
            <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '800' }}>View Activity Log</Text>
          </TouchableOpacity>
        </View>
      </View>
    </>
  );
}

export function NotificationOverlay() {
  const { scope } = useContext(NotifCtx);
  return scope === 'admin' ? <AdminNotificationOverlay /> : <UserNotificationOverlay />;
}

/* i18n-probe t('i18n.auto.probe') */
