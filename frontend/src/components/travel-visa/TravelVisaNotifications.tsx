import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, Switch, ActivityIndicator, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import api from '../../services/api';

export default function TravelVisaNotifications({ userId }: { userId: string }) {
  const { colors } = useTheme();
  const { t } = useLanguage();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [prefs, setPrefs] = useState<any>(null);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showPrefs, setShowPrefs] = useState(false);
  const [pageError, setPageError] = useState('');
  const [actionError, setActionError] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setPageError('');
    try {
      const [prefsRes, notifsRes] = await Promise.all([
        api.get(`/travel-visa/notifications/prefs/${userId}`),
        api.get(`/travel-visa/notifications/${userId}`),
      ]);
      setPrefs(prefsRes.data?.preferences || {});
      setNotifications(notifsRes.data?.notifications || []);
      setUnreadCount(notifsRes.data?.unread_count || 0);
    } catch (e: any) {
      setPageError(e?.response?.data?.detail || tx('travelVisa.notifications.errors.loadFailed', 'Unable to load notifications.'));
      setPrefs({});
      setNotifications([]);
      setUnreadCount(0);
    }
    setLoading(false);
  }, [userId]);

  useEffect(() => { loadData(); }, [loadData]);

  const updatePref = useCallback(async (key: string, value: boolean) => {
    setActionError('');
    const previousPrefs = prefs;
    const updated = { ...prefs, [key]: value };
    setPrefs(updated);
    setSaving(true);
    try {
      await api.post('/travel-visa/notifications/prefs', { user_id: userId, ...updated });
    } catch (e: any) {
      setPrefs(previousPrefs);
      setActionError(e?.response?.data?.detail || tx('travelVisa.notifications.errors.prefUpdateFailed', 'Preference update failed.'));
    }
    setSaving(false);
  }, [prefs, userId]);

  const markAllRead = useCallback(async () => {
    setActionError('');
    try {
      await api.post('/travel-visa/notifications/read', { user_id: userId });
      setUnreadCount(0);
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    } catch (e: any) {
      setActionError(e?.response?.data?.detail || tx('travelVisa.notifications.errors.markReadFailed', 'Unable to mark notifications as read.'));
    }
  }, [userId]);

  const notifIcon = (type: string) => {
    const map: Record<string, string> = {
      daily_lessons: 'book-outline', challenge_invite: 'flash-outline',
      streak_reminder: 'flame-outline', new_content: 'sparkles-outline',
      achievement: 'trophy-outline',
    };
    return (map[type] || 'notifications-outline') as any;
  };

  if (loading) {
    return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={colors.primary} /></View>;
  }

  const PREF_ITEMS = [
    { key: 'daily_lessons', label: tx('travelVisa.notifications.prefs.dailyLessons', 'Daily Lesson Alerts'), desc: tx('travelVisa.notifications.prefs.dailyLessonsDesc', 'Get notified about 2 new lessons each day'), icon: 'book-outline' },
    { key: 'new_content', label: tx('travelVisa.notifications.prefs.newContent', 'New Content'), desc: tx('travelVisa.notifications.prefs.newContentDesc', 'Notifications for new categories and quizzes'), icon: 'sparkles-outline' },
    { key: 'challenge_invites', label: tx('travelVisa.notifications.prefs.challengeInvites', 'Challenge Invites'), desc: tx('travelVisa.notifications.prefs.challengeInvitesDesc', 'When friends challenge you to quizzes'), icon: 'flash-outline' },
    { key: 'streak_reminders', label: tx('travelVisa.notifications.prefs.streakReminders', 'Streak Reminders'), desc: tx('travelVisa.notifications.prefs.streakRemindersDesc', 'Daily reminders to keep your learning streak'), icon: 'flame-outline' },
    { key: 'weekly_digest', label: tx('travelVisa.notifications.prefs.weeklyDigest', 'Weekly Digest'), desc: tx('travelVisa.notifications.prefs.weeklyDigestDesc', 'Summary of your progress each week'), icon: 'analytics-outline' },
    { key: 'email_notifications', label: tx('travelVisa.notifications.prefs.emailNotifications', 'Email Notifications'), desc: tx('travelVisa.notifications.prefs.emailNotificationsDesc', 'Receive notifications via email'), icon: 'mail-outline' },
    { key: 'push_notifications', label: tx('travelVisa.notifications.prefs.pushNotifications', 'Push Notifications'), desc: tx('travelVisa.notifications.prefs.pushNotificationsDesc', 'Browser/device push notifications'), icon: 'notifications-outline' },
  ];

  return (
    <View data-testid="tv-notifications">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Text style={{ fontSize: 16, fontWeight: '700', color: colors.text }}>{tx('travelVisa.notifications.header.title', 'Notifications')}</Text>
          {unreadCount > 0 && (
            <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10, backgroundColor: colors.error }}>
              <Text style={{ fontSize: 11, fontWeight: '700', color: colors.primaryText }}>{unreadCount}</Text>
            </View>
          )}
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {unreadCount > 0 && (
            <TouchableOpacity data-testid="tv-notif-mark-read-btn" onPress={markAllRead}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: colors.surfaceHover, borderWidth: 1, borderColor: colors.border }}>
              <Ionicons name="checkmark-done" size={14} color={colors.primary} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.primary }}>{tx('travelVisa.notifications.actions.markAllRead', 'Mark All Read')}</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity data-testid="tv-notif-prefs-toggle" onPress={() => setShowPrefs(!showPrefs)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, backgroundColor: showPrefs ? colors.primary : colors.surfaceHover, borderWidth: 1, borderColor: showPrefs ? colors.primary : colors.border }}>
            <Ionicons name="settings-outline" size={14} color={showPrefs ? colors.primaryText : colors.text} />
            <Text style={{ fontSize: 12, fontWeight: '600', color: showPrefs ? colors.primaryText : colors.text }}>{tx('travelVisa.notifications.actions.preferences', 'Preferences')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      {!!pageError && (
        <View data-testid="tv-notif-load-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.error, '55'), backgroundColor: colors.errorSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.errorText, fontWeight: '700', marginBottom: 8 }}>{pageError}</Text>
          <TouchableOpacity data-testid="tv-notif-retry-load-btn" onPress={() => void loadData()} style={{ alignSelf: 'flex-start', borderRadius: 8, backgroundColor: colors.error, paddingHorizontal: 10, paddingVertical: 6 }}>
            <Text style={{ fontSize: 11, color: colors.errorTextInverse || colors.primaryText, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
          </TouchableOpacity>
        </View>
      )}
      {!!actionError && (
        <View data-testid="tv-notif-action-error" style={{ borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.warning, '55'), backgroundColor: colors.warningSoft, padding: 10, marginBottom: 12 }}>
          <Text style={{ fontSize: 11, color: colors.warningText, fontWeight: '700' }}>{actionError}</Text>
        </View>
      )}

      {/* Preferences Panel */}
      {showPrefs && (
        <View data-testid="tv-notif-prefs-panel" style={{
          padding: 16, borderRadius: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, marginBottom: 16,
        }}>
          <Text style={{ fontSize: 14, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('travelVisa.notifications.prefs.title', 'Notification Preferences')}</Text>
          {PREF_ITEMS.map(item => (
            <View key={item.key} style={{
              flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10,
              borderBottomWidth: 1, borderBottomColor: colors.border,
            }}>
              <Ionicons name={item.icon as any} size={18} color={colors.primary} />
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{item.label}</Text>
                <Text style={{ fontSize: 11, color: colors.textMuted }}>{item.desc}</Text>
              </View>
              <Switch
                value={prefs?.[item.key] ?? true}
                onValueChange={(val) => updatePref(item.key, val)}
                trackColor={{ false: colors.border, true: colors.primary + '60' }}
                thumbColor={prefs?.[item.key] ? colors.primary : colors.textMuted}
              />
            </View>
          ))}
          {saving && <Text style={{ fontSize: 11, color: colors.primary, marginTop: 8 }}>{tx('common.saving', 'Saving...')}</Text>}
        </View>
      )}

      {/* Notification List */}
      {notifications.length === 0 ? (
        <View style={{ padding: 30, alignItems: 'center', borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border }}>
          <Ionicons name="notifications-off-outline" size={48} color={colors.textMuted} />
          <Text style={{ fontSize: 16, fontWeight: '600', color: colors.text, marginTop: 12 }}>{tx('travelVisa.notifications.states.noneYet', 'No notifications yet')}</Text>
          <Text style={{ fontSize: 13, color: colors.textMuted, marginTop: 4, textAlign: 'center' }}>
            {tx('travelVisa.notifications.states.noneYetDescription', 'Start learning to receive daily lesson alerts, challenge invites, and streak reminders.')}
          </Text>
        </View>
      ) : (
        notifications.map((notif, i) => (
          <View data-testid={`tv-notif-item-${i}`} key={i} style={{
            flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14, borderRadius: 12, marginBottom: 6,
            backgroundColor: notif.read ? colors.card : colors.primarySoft,
            borderWidth: 1, borderColor: (globalThis as any).__alphaColor(notif.read ? colors.border : colors.primary, '25'),
          }}>
            <View style={{
              width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(notif.read ? colors.surfaceHover : colors.primary, '20'),
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Ionicons name={notifIcon(notif.type)} size={16} color={notif.read ? colors.textMuted : colors.primary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, fontWeight: '600', color: colors.text }}>{notif.title}</Text>
              <Text style={{ fontSize: 12, color: colors.textMuted, marginTop: 2, lineHeight: 18 }}>{notif.message}</Text>
              <Text style={{ fontSize: 10, color: colors.textMuted, marginTop: 4 }}>
                {new Date(notif.created_at).toLocaleDateString()}
              </Text>
            </View>
            {!notif.read && (
              <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary, marginTop: 4 }} />
            )}
          </View>
        ))
      )}
    </View>
  );
}
