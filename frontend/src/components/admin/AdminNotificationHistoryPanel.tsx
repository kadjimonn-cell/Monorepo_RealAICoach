import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { humanizeAdminToken, normalizeAdminRuntimeCopy, normalizeAdminStatusTone } from '../../i18n/adminCopyGuard';

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'var(--app-error)',
  warning: 'var(--app-warning)' as any,
  info: 'var(--app-info)' as any,
};

export default function AdminNotificationHistoryPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const colors = useAdminTheme();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [typeFilter, setTypeFilter] = useState('all');

  const load = useCallback(async (nextType = typeFilter) => {
    setLoading(true);
    try {
      const res = await api.get(`/admin/notifications/history?limit=60&days=7&type_filter=${encodeURIComponent(nextType)}`);
      setData(res.data || null);
    } catch (e) {
      console.error('Admin notification history load error:', e);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    load(typeFilter);
  }, [load, typeFilter]);

  const summary = useMemo(() => data?.summary || {}, [data]);
  const notifications = useMemo(() => (Array.isArray(data?.notifications) ? data.notifications : []), [data]);
  const typeKeys = useMemo(() => ['all', ...Object.keys(summary.types || {}).slice(0, 6)], [summary.types]);
  const summaryCards = useMemo(() => [
    { id: 'total', label: tx('admin.adminNotificationHistoryPanel.summary.total', 'Total'), value: summary.total || 0, color: colors.primary, icon: 'notifications' },
    { id: 'critical', label: tx('admin.adminNotificationHistoryPanel.summary.critical', 'Critical'), value: summary.critical || 0, color: colors.error, icon: 'alert-circle' },
    { id: 'warning', label: tx('admin.adminNotificationHistoryPanel.summary.warning', 'Warning'), value: summary.warning || 0, color: colors.warningText, icon: 'warning' },
    { id: 'info', label: tx('admin.adminNotificationHistoryPanel.summary.info', 'Info'), value: summary.info || 0, color: colors.primary, icon: 'information-circle' },
  ], [colors.error, colors.primary, colors.warningText, summary.critical, summary.info, summary.total, summary.warning, tx]);

  const normalizedNotifications = useMemo(() => notifications.map((item: any, idx: number) => ({
    ...item,
    title: normalizeAdminRuntimeCopy(item?.title, tx('admin.adminNotificationHistoryPanel.item.titleFallback', `Admin notification ${idx + 1}`)),
    message: normalizeAdminRuntimeCopy(item?.message, tx('admin.adminNotificationHistoryPanel.item.messageFallback', 'Notification details unavailable.')),
    severityLabel: normalizeAdminStatusTone(item?.severity, 'INFO'),
    typeLabel: humanizeAdminToken(item?.type, tx('admin.adminNotificationHistoryPanel.item.typeFallback', 'System')),
    sourceLabel: humanizeAdminToken(item?.source, tx('admin.adminNotificationHistoryPanel.item.sourceFallback', 'System')),
    deliveryStatusLabel: humanizeAdminToken(item?.delivery_status, tx('admin.adminNotificationHistoryPanel.item.deliveryFallback', 'Delivered')),
  })), [notifications, tx]);

  return (
    <ScrollView contentContainerStyle={{ gap: 12 }} data-testid="admin-notification-history-panel" testID="admin-notification-history-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <View>
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '800' }} data-testid="admin-notification-history-title" testID="admin-notification-history-title">{tx('admin.adminNotificationHistoryPanel.auto.text.001', 'Notification History')}</Text>
          <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="admin-notification-history-subtitle" testID="admin-notification-history-subtitle">{tx('admin.adminNotificationHistoryPanel.auto.text.002', 'Seven-day admin alert archive across security, payments, signups, expiries, and push events.')}</Text>
        </View>
        <TouchableOpacity onPress={() => load(typeFilter)} data-testid="admin-notification-history-refresh" testID="admin-notification-history-refresh" style={{ padding: 8, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(colors.primary, '15') }}>
          <Ionicons name="refresh" size={16} color={'var(--app-primary)'} />
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="admin-notification-history-summary" testID="admin-notification-history-summary">
        {summaryCards.map((item) => (
          <View key={item.id} style={{ flex: 1, minWidth: 120, backgroundColor: (globalThis as any).__alphaColor(item.color, '10'), borderRadius: 12, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(item.color, '20'), padding: 12 }} data-testid={`admin-notification-history-summary-${item.id}`} testID={`admin-notification-history-summary-${item.id}`}>
            <Ionicons name={item.icon as any} size={14} color={item.color} />
            <Text style={{ color: item.color, fontSize: 20, fontWeight: '800', marginTop: 6 }}>{item.value}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }}>{item.label}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="admin-notification-history-filters" testID="admin-notification-history-filters">
        {typeKeys.map((type) => (
          <TouchableOpacity
            key={type}
            onPress={() => setTypeFilter(type)}
            data-testid={`admin-notification-history-filter-${type}`} testID={`admin-notification-history-filter-${type}`}
            style={{ paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, backgroundColor: typeFilter === type ? 'var(--app-primary)' : 'var(--app-primary)', borderWidth: 1, borderColor: typeFilter === type ? 'var(--app-primary)' : 'var(--app-text)' }}
          >
            <Text style={{ color: typeFilter === type ? 'var(--app-primary-text)' : 'var(--app-primary-text)', fontSize: 10, fontWeight: '700' }}>{type === 'all' ? tx('admin.adminNotificationHistoryPanel.filter.all', 'ALL') : humanizeAdminToken(type, tx('admin.adminNotificationHistoryPanel.item.typeFallback', 'System')).toUpperCase()}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={{ backgroundColor: colors.bg, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 }} data-testid="admin-notification-history-list-card" testID="admin-notification-history-list-card">
        {loading ? (
          <ActivityIndicator color={'var(--app-primary)'} style={{ marginVertical: 20 }} />
        ) : normalizedNotifications.length === 0 ? (
          <Text style={{ color: colors.textMuted, fontSize: 11 }}>{tx('admin.adminNotificationHistoryPanel.auto.text.003', 'No notifications found for the selected filter.')}</Text>
        ) : normalizedNotifications.map((item: any, idx: number) => {
          const tone = SEVERITY_COLOR[String(item.severity || 'info')] || 'var(--app-primary)';
          return (
            <View key={`${item.id}-${idx}`} style={{ paddingVertical: 10, borderBottomWidth: idx < notifications.length - 1 ? 1 : 0, borderBottomColor: (globalThis as any).__alphaColor(colors.border, '30') }} data-testid={`admin-notification-history-item-${idx}`} testID={`admin-notification-history-item-${idx}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700', flex: 1 }}>{item.title}</Text>
                <View style={{ backgroundColor: (globalThis as any).__alphaColor(tone, '15'), borderRadius: 999, paddingHorizontal: 8, paddingVertical: 3 }}>
                  <Text style={{ color: tone, fontSize: 9, fontWeight: '800' }}>{item.severityLabel}</Text>
                </View>
              </View>
              <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 4 }}>{item.message}</Text>
              <Text style={{ color: colors.textMuted, fontSize: 9, marginTop: 5 }}>
                {item.typeLabel} • {item.sourceLabel} • {item.deliveryStatusLabel} • {item.timestamp || 'n/a'}
              </Text>
            </View>
          );
        })}
      </View>
    </ScrollView>
  );
}