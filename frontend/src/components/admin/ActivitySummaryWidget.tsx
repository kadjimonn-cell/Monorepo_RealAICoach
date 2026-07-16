import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

import { getAdminColors } from '../../hooks/useAdminTheme';
function getC(dark) {
  const A = getAdminColors(dark);
  return { bg: A.bg, card: A.card, card2: A.cardSoft, border: A.border, text: A.text, muted: A.textDim, sec: A.textMuted, green: 'var(--app-success)', red: 'var(--app-error)', blue: 'var(--app-primary)', yellow: 'var(--app-warning)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)', orange: 'var(--app-warning)', indigo: 'var(--app-primary)', pink: 'var(--app-primary)', lime: 'var(--app-primary)', teal: 'var(--app-primary)' };
}
const C = getC(true);

export default function ActivitySummaryWidget({ colors, onViewFeed }: { colors: any; onViewFeed?: () => void }) {
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const EVENT_ICONS: Record<string, { icon: string; color: string }> = {
    login: { icon: 'log-in-outline', color: C.cyan },
    page_view: { icon: 'eye-outline', color: C.blue },
    feature_usage: { icon: 'flash-outline', color: C.purpleText },
    completion: { icon: 'trophy-outline', color: C.yellow },
    error: { icon: 'warning-outline', color: C.red },
    admin_action: { icon: 'shield-checkmark-outline', color: 'var(--app-primary)' }, // @theme-ok residual semantic hex (reviewed)
    upgrade: { icon: 'star-outline', color: colors.warningText },
    api_call: { icon: 'code-slash-outline', color: C.green },
  };
  const { data, loading } = useLiveQuery('/admin/live-activity/summary', {
    entity: 'live-activity',
    pollInterval: 20000,
  });

  if (loading && !data) {
    return (
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="activity-summary-widget-loading" testID="activity-summary-widget-loading">
        <ActivityIndicator color={C.cyan} />
      </View>
    );
  }

  const summary = data || {};
  const trendIcon = summary.trend === 'up' ? 'trending-up' : summary.trend === 'down' ? 'trending-down' : 'remove-outline';
  const trendColor = summary.trend === 'up' ? C.green : summary.trend === 'down' ? C.red : C.sec;

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border, overflow: 'hidden' }} data-testid="activity-summary-widget" testID="activity-summary-widget">
      {/* Header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1, borderBottomColor: C.border }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '18'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="pulse-outline" size={16} color={C.cyan} />
          </View>
          <View>
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }}>{tx('admin.activitySummaryWidget.header.title', 'Activity Summary')}</Text>
            <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.activitySummaryWidget.header.subtitle', 'Last 24 hours')}</Text>
          </View>
        </View>
        {onViewFeed && (
          <TouchableOpacity onPress={onViewFeed} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }} data-testid="activity-summary-view-feed" testID="activity-summary-view-feed">
            <Text style={{ fontSize: 11, color: C.cyan, fontWeight: '600' }}>{tx('admin.activitySummaryWidget.actions.viewFeed', 'View Feed')}</Text>
            <Ionicons name="chevron-forward" size={12} color={C.cyan} />
          </TouchableOpacity>
        )}
      </View>

      {/* KPI Row */}
      <View style={{ flexDirection: 'row', padding: 16, gap: 12 }}>
        <View style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(C.cyan, '10'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <Text style={{ fontSize: 22, fontWeight: '800', color: C.cyan, fontVariant: ['tabular-nums'] }}>{summary.current_total ?? 0}</Text>
          <Text style={{ fontSize: 9, color: C.muted, fontWeight: '600', textTransform: 'uppercase', marginTop: 2 }}>{tx('admin.activitySummaryWidget.kpi.events', 'Events')}</Text>
        </View>
        <View style={{ flex: 1, backgroundColor: (globalThis as any).__alphaColor(trendColor, '10'), borderRadius: 10, padding: 12, alignItems: 'center' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Ionicons name={trendIcon as any} size={16} color={trendColor} />
            <Text style={{ fontSize: 16, fontWeight: '800', color: trendColor, fontVariant: ['tabular-nums'] }}>
              {summary.change_percent > 0 ? '+' : ''}{summary.change_percent ?? 0}%
            </Text>
          </View>
          <Text style={{ fontSize: 9, color: C.muted, fontWeight: '600', textTransform: 'uppercase', marginTop: 2 }}>{tx('admin.activitySummaryWidget.kpi.vsPrevious', 'vs Previous')}</Text>
        </View>
      </View>

      {/* Top Event Types */}
      {summary.top_event_types?.length > 0 && (
        <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.activitySummaryWidget.sections.topEvents', 'Top Events')}</Text>
          <View style={{ gap: 6 }}>
            {summary.top_event_types.slice(0, 4).map((t: any) => {
              const config = EVENT_ICONS[t.type] || { icon: 'ellipse-outline', color: C.muted };
              const maxCount = summary.top_event_types[0]?.count || 1;
              return (
                <View key={t.type} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid={`summary-event-type-${t.type}`} testID={`summary-event-type-${t.type}`}>
                  <Ionicons name={config.icon as any} size={12} color={config.color} />
                  <Text style={{ fontSize: 11, color: C.sec, width: 70 }}>{t.type.replace('_', ' ')}</Text>
                  <View style={{ flex: 1, height: 6, backgroundColor: C.bg, borderRadius: 3, overflow: 'hidden' }}>
                    <View style={{ width: `${(t.count / maxCount) * 100}%`, height: '100%', backgroundColor: (globalThis as any).__alphaColor(config.color, '60'), borderRadius: 3 }} />
                  </View>
                  <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700', fontVariant: ['tabular-nums'], width: 30, textAlign: 'right' }}>{t.count}</Text>
                </View>
              );
            })}
          </View>
        </View>
      )}

      {/* Recent Events */}
      {summary.recent_events?.length > 0 && (
        <View style={{ borderTopWidth: 1, borderTopColor: C.border, padding: 16 }}>
          <Text style={{ fontSize: 10, color: C.muted, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>{tx('admin.activitySummaryWidget.sections.latest', 'Latest')}</Text>
          {summary.recent_events.slice(0, 3).map((e: any, i: number) => {
            const config = EVENT_ICONS[e.event_type] || { icon: 'ellipse-outline', color: C.muted };
            return (
              <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 }} data-testid={`summary-recent-${i}`} testID={`summary-recent-${i}`}>
                <View style={{ width: 20, height: 20, borderRadius: 5, backgroundColor: (globalThis as any).__alphaColor(config.color, '15'), alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={config.icon as any} size={10} color={config.color} />
                </View>
                <Text style={{ flex: 1, fontSize: 11, color: C.sec }} numberOfLines={1}>{e.detail}</Text>
                <Text style={{ fontSize: 9, color: C.muted }}>{e.user_email?.split('@')[0]}</Text>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}
