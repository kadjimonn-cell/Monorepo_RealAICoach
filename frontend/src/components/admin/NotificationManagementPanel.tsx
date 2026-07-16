import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const _C = getC(true);

const tx = (_key: string, fallback: string) => fallback;

export default function NotificationManagementPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  const C = getC(darkMode);
  const { data: summary, loading, refetch: fetchSummary } = useLiveQuery('/notification-engine/summary', { entity: 'notifications', pollInterval: 30000 });
  const [broadcastTitle, setBroadcastTitle] = useState('');
  const [broadcastBody, setBroadcastBody] = useState('');
  const [sending, setSending] = useState(false);
  const [testSent, setTestSent] = useState(false);

  const sendTestNotification = async () => {
    setSending(true);
    try {
      await api.post('/notification-engine/test');
      setTestSent(true);
      setTimeout(() => setTestSent(false), 3000);
      fetchSummary();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/NotificationManagementPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSending(false);
  };

  const sendBroadcast = async () => {
    if (!broadcastTitle.trim() || !broadcastBody.trim()) return;
    setSending(true);
    try {
      await api.post('/admin/notifications/broadcast', {
        title: broadcastTitle.trim(),
        body: broadcastBody.trim(),
      });
      setBroadcastTitle('');
      setBroadcastBody('');
      fetchSummary();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/NotificationManagementPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSending(false);
  };

  const typeColors: Record<string, string> = {
    new_content: C.purple, expiring_soon: C.yellow, trending: C.green,
    booking_created: C.blue, booking_cancelled: C.red, meeting_reminder: C.yellow,
    employer_approved: C.green, employer_denied: C.red, employer_pending: C.yellow,
    interview_scheduled: C.blue, test: C.purple, general: C.blue,
  };

  return (
    <View data-testid="notification-management-panel" testID="notification-management-panel">
      <Text style={{ color: colors.primaryText, fontSize: 16, fontWeight: '800', marginBottom: 16 }}>{tx('admin.notificationManagementPanel.auto.text.001', 'Notification Management')}</Text>

      {loading ? (
        <ActivityIndicator color={C.blue} style={{ padding: 20 }} />
      ) : (
        <>
          {/* Summary Stats */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
            {[
              { label: 'Total Sent', value: summary?.total || 0, color: C.blue, icon: 'notifications' },
              { label: 'Unread', value: summary?.total_unread || 0, color: C.red, icon: 'mail-unread' },
              { label: 'Types Active', value: Object.keys(summary?.by_type || {}).length, color: C.purpleText, icon: 'layers' },
            ].map(s => (
              <View key={s.label} style={{ flex: 1, minWidth: 140, backgroundColor: (globalThis as any).__alphaColor(s.color, '10'), borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '20') }} data-testid={`notif-mgmt-stat-${s.label.toLowerCase().replace(' ','-')}`} testID={`notif-mgmt-stat-${s.label.toLowerCase().replace(' ','-')}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name={s.icon as any} size={18} color={s.color} />
                  <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase' }}>{s.label}</Text>
                </View>
                <Text style={{ color: s.color, fontSize: 28, fontWeight: '800', marginTop: 6 }}>{s.value}</Text>
              </View>
            ))}
          </View>

          {/* Notification Types Breakdown */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border, marginBottom: 20 }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.notificationManagementPanel.auto.text.002', 'Notification Types')}</Text>
            <View style={{ gap: 6 }}>
              {Object.entries(summary?.by_type || {}).map(([type, data]: [string, any]) => (
                <View key={type} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: typeColors[type] || C.muted }} />
                    <Text style={{ color: C.text, fontSize: 12, fontWeight: '600' }}>{type.replace(/_/g, ' ')}</Text>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 12 }}>
                    <Text style={{ color: C.muted, fontSize: 11 }}>{data.count} total</Text>
                    <Text style={{ color: data.unread > 0 ? C.red : C.green, fontSize: 11, fontWeight: '600' }}>{data.unread} unread</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>

          {/* Quick Actions */}
          <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20 }}>
            <TouchableOpacity
              onPress={sendTestNotification}
              disabled={sending}
              style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(C.purple, '15'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '30') }}
              data-testid="send-test-notification-btn" testID="send-test-notification-btn"
            >
              <Ionicons name={testSent ? 'checkmark-circle' : 'flask'} size={20} color={testSent ? C.green : C.purple} />
              <Text style={{ color: testSent ? C.green : C.purple, fontSize: 12, fontWeight: '700', marginTop: 4 }}>
                {testSent ? 'Test Sent!' : 'Send Test'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={fetchSummary}
              style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(C.blue, '15'), borderRadius: 12, padding: 14, alignItems: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '30') }}
              data-testid="refresh-notif-stats-btn" testID="refresh-notif-stats-btn"
            >
              <Ionicons name="refresh" size={20} color={C.blue} />
              <Text style={{ color: C.blue, fontSize: 12, fontWeight: '700', marginTop: 4 }}>{tx('admin.notificationManagementPanel.auto.text.003', 'Refresh Stats')}</Text>
            </TouchableOpacity>
          </View>

          {/* Broadcast Notification */}
          <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: C.border }}>
            <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginBottom: 12 }}>{tx('admin.notificationManagementPanel.auto.text.004', 'Broadcast Notification')}</Text>
            <Text style={{ color: C.muted, fontSize: 11, marginBottom: 10 }}>{tx('admin.notificationManagementPanel.auto.text.005', 'Send a notification to all users on the platform.')}</Text>
            <TextInput
              value={broadcastTitle}
              onChangeText={setBroadcastTitle}
              placeholder={tx('admin.notificationManagementPanel.auto.placeholder.001', 'Notification title...')}
              placeholderTextColor={C.muted}
              style={{ backgroundColor: C.bg, color: C.text, borderRadius: 10, padding: 12, fontSize: 13, marginBottom: 8, borderWidth: 1, borderColor: C.border }}
              data-testid="broadcast-title-input" testID="broadcast-title-input"
            />
            <TextInput
              value={broadcastBody}
              onChangeText={setBroadcastBody}
              placeholder={tx('admin.notificationManagementPanel.auto.placeholder.002', 'Notification body...')}
              placeholderTextColor={C.muted}
              multiline
              numberOfLines={3}
              style={{ backgroundColor: C.bg, color: C.text, borderRadius: 10, padding: 12, fontSize: 13, marginBottom: 12, borderWidth: 1, borderColor: C.border, minHeight: 60, textAlignVertical: 'top' }}
              data-testid="broadcast-body-input" testID="broadcast-body-input"
            />
            <TouchableOpacity
              onPress={sendBroadcast}
              disabled={sending || !broadcastTitle.trim() || !broadcastBody.trim()}
              style={{ backgroundColor: C.blue, borderRadius: 10, paddingVertical: 12, alignItems: 'center', opacity: sending || !broadcastTitle.trim() || !broadcastBody.trim() ? 0.5 : 1 }}
              data-testid="broadcast-send-btn" testID="broadcast-send-btn"
            >
              <Text style={{ color: colors.primaryText, fontSize: 13, fontWeight: '700' }}>{sending ? 'Sending...' : 'Send Broadcast'}</Text>
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );
}
