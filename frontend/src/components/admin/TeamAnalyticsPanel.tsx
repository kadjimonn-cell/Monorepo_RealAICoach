import React, { useMemo, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

const ROLE_COLORS: Record<string, string> = {
  owner: 'var(--app-warning)', // @theme-ok brand/role/state identifier
  admin: 'var(--app-error)', // @theme-ok brand/role/state identifier
  manager: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  member: 'var(--app-primary)', // @theme-ok brand/role/state identifier
  viewer: 'var(--app-text-muted)', // @theme-ok brand/role/state identifier
};

const ACTION_ICONS: Record<string, string> = {
  team_created: 'add-circle',
  member_invited: 'person-add',
  member_removed: 'person-remove',
  role_changed: 'swap-horizontal',
  team_updated: 'settings',
  team_deleted: 'trash',
};

export default function TeamAnalyticsPanel({ colors: _colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { data, loading: overviewLoading, refetch: refetchOverview } = useLiveQuery('/team-analytics/overview', {
    entity: 'team-analytics',
    pollInterval: 60000,
  });
  const { data: enhanced, loading: enhancedLoading, refetch: refetchEnhanced } = useLiveQuery('/team-analytics-enhanced/enhanced', {
    entity: 'team-analytics',
    pollInterval: 60000,
  });
  const loading = overviewLoading || enhancedLoading;
  const [view, setView] = useState<'overview' | 'engagement' | 'activity'>('overview');

  const palette = useMemo(() => ({
    card: colors.surface,
    cardAlt: colors.surfaceHover,
    border: colors.border,
    text: colors.text,
    textSec: colors.textSec,
    textMuted: colors.textMuted,
    primary: colors.primary,
    primarySoft: colors.primarySoft || `${colors.primary}14`,
    primaryText: colors.primaryText,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
  }), [colors]);

  const load = async () => {
    await Promise.allSettled([refetchOverview(), refetchEnhanced()]);
  };

  if (loading) {
    return <ActivityIndicator color={palette.primary} />;
  }

  if (!data) {
    return <Text style={{ color: palette.textMuted, textAlign: 'center', padding: 20 }}>{tx('admin.teamAnalyticsPanel.auto.text.001', 'Failed to load')}</Text>;
  }

  const roleMax = Math.max(...(data.role_distribution || []).map((role: any) => role.count), 1);

  return (
    <View data-testid="team-analytics-panel" testID="team-analytics-panel">
      <AutoFixBanner domain="team_analytics" />

      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <View>
          <Text style={{ color: palette.text, fontSize: 18, fontWeight: '800' }}>{tx('admin.teamAnalyticsPanel.auto.text.002', 'Team Analytics')}</Text>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>{tx('admin.teamAnalyticsPanel.auto.text.003', 'Team growth, engagement scores, and activity insights')}</Text>
        </View>

        <TouchableOpacity onPress={() => { void load(); }} accessibilityLabel={tx('admin.teamAnalyticsPanel.auto.accessibility.001', 'Refresh team analytics data')}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            gap: 4,
            backgroundColor: palette.cardAlt,
            paddingHorizontal: 12,
            paddingVertical: 8,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: palette.border,
          }}
          accessibilityLabel={tx('admin.teamAnalyticsPanel.auto.accessibility.002', 'Refresh')}
          data-testid="team-analytics-refresh-button"
          testID="team-analytics-refresh-button"
        >
          <Ionicons name="refresh" size={14} color={palette.textMuted} />
          <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('admin.teamAnalyticsPanel.auto.text.004', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      <View style={{ flexDirection: 'row', gap: 8, marginTop: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <KPI label="Total Teams" value={data.total_teams} color={palette.primary} icon="people" textMuted={palette.textMuted} />
        <KPI label="Total Members" value={data.total_members} color={palette.successText} icon="person-add" textMuted={palette.textMuted} />
        <KPI label="Avg Size" value={data.avg_team_size} color={colors.accent || 'var(--app-primary)'} icon="stats-chart" textMuted={palette.textMuted} />
        <KPI label="Activity (7d)" value={data.recent_activity_7d} color={palette.warningText} icon="pulse" textMuted={palette.textMuted} />
      </View>

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 16 }}>
        {(['overview', 'engagement', 'activity'] as const).map((item) => {
          const active = view === item;
          return (
            <TouchableOpacity
              key={item}
              onPress={() => setView(item)}
              data-testid={`analytics-view-${item}`}
              testID={`analytics-view-${item}`}
              style={{
                paddingHorizontal: 14,
                paddingVertical: 7,
                borderRadius: 8,
                backgroundColor: active ? palette.primary : palette.cardAlt,
                borderWidth: 1,
                borderColor: active ? palette.primary : palette.border,
              }}
            >
              <Text style={{ color: active ? palette.primaryText : palette.textSec, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' }}>{item}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {view === 'overview' && (
        <View>
          <PanelCard title="Role Distribution" palette={palette} testId="team-analytics-role-distribution-card">
            {(data.role_distribution || []).map((role: any) => {
              const roleColor = ROLE_COLORS[role.role] || 'var(--app-text-muted)';
              const width = Math.max((role.count / roleMax) * 100, 8);
              return (
                <View key={role.role} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 10 }}>
                  <View style={{ width: 60 }}>
                    <Text style={{ color: roleColor, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{role.role}</Text>
                  </View>
                  <View style={{ flex: 1, height: 22, backgroundColor: palette.cardAlt, borderRadius: 6, overflow: 'hidden' }}>
                    <View style={{ height: 22, width: `${width}%` as any, backgroundColor: `${roleColor}24`, borderRadius: 6, justifyContent: 'center', paddingLeft: 8 }}>
                      <Text style={{ color: roleColor, fontSize: 10, fontWeight: '800' }}>{role.count}</Text>
                    </View>
                  </View>
                </View>
              );
            })}
            {(data.role_distribution || []).length === 0 ? <EmptyMessage label="No roles data" muted={palette.textMuted} /> : null}
          </PanelCard>

          <PanelCard title="Largest Teams" palette={palette} testId="team-analytics-largest-teams-card">
            {(data.top_teams || []).map((team: any, index: number) => (
              <View
                key={team.name}
                data-testid={`top-team-${index}`}
                testID={`top-team-${index}`}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  paddingVertical: 8,
                  borderBottomWidth: index < (data.top_teams?.length || 0) - 1 ? 1 : 0,
                  borderBottomColor: palette.border,
                }}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: palette.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ color: palette.primary, fontSize: 10, fontWeight: '800' }}>#{index + 1}</Text>
                  </View>
                  <Text style={{ color: palette.text, fontSize: 13, fontWeight: '600' }}>{team.name}</Text>
                </View>
                <Text style={{ color: palette.textMuted, fontSize: 12, fontWeight: '700' }}>{team.members} members</Text>
              </View>
            ))}
            {(data.top_teams || []).length === 0 ? <EmptyMessage label="No teams yet" muted={palette.textMuted} /> : null}
          </PanelCard>

          {(enhanced?.member_growth || []).length > 0 ? (
            <PanelCard title="Member Growth (30d)" palette={palette} testId="team-analytics-member-growth-card">
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 80 }}>
                  {(enhanced.member_growth || []).map((day: any, index: number) => {
                    const maxActions = Math.max(...enhanced.member_growth.map((entry: any) => entry.actions), 1);
                    const height = Math.max((day.actions / maxActions) * 60, 4);
                    return (
                      <View key={index} style={{ alignItems: 'center' }}>
                        <View style={{ width: 16, height, backgroundColor: palette.primarySoft, borderRadius: 3 }} />
                        <Text style={{ color: palette.textMuted, fontSize: 7, marginTop: 2 }}>{day.date.slice(5)}</Text>
                      </View>
                    );
                  })}
                </View>
              </ScrollView>
            </PanelCard>
          ) : null}
        </View>
      )}

      {view === 'engagement' && (
        <View>
          <PanelCard title="Team Engagement Scores" palette={palette} testId="team-analytics-engagement-card">
            {(enhanced?.team_engagement || []).map((team: any, index: number) => {
              const score = team.engagement_score;
              const scoreColor = score >= 70 ? palette.success : score >= 40 ? palette.warning : palette.error;
              return (
                <View
                  key={team.team_id}
                  data-testid={`engagement-team-${index}`}
                  testID={`engagement-team-${index}`}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    padding: 12,
                    marginBottom: 6,
                    borderRadius: 10,
                    backgroundColor: palette.cardAlt,
                    borderWidth: 1,
                    borderColor: palette.border,
                    borderLeftWidth: 3,
                    borderLeftColor: scoreColor,
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={{ color: palette.text, fontSize: 13, fontWeight: '700' }}>{team.name}</Text>
                    <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                      <Text style={{ color: palette.textMuted, fontSize: 9 }}>{team.members} members</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 9 }}>{team.actions_30d} actions (30d)</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 9 }}>{team.custom_roles} custom roles</Text>
                    </View>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <View style={{ width: 48, height: 48, borderRadius: 24, borderWidth: 3, borderColor: scoreColor, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: scoreColor, fontSize: 16, fontWeight: '800' }}>{score}</Text>
                    </View>
                    <Text style={{ color: palette.textMuted, fontSize: 8, marginTop: 2 }}>{tx('admin.teamAnalyticsPanel.auto.text.005', 'score')}</Text>
                  </View>
                </View>
              );
            })}
            {(enhanced?.team_engagement || []).length === 0 ? <EmptyMessage label="No engagement data yet" muted={palette.textMuted} /> : null}
          </PanelCard>

          {(enhanced?.top_active_users || []).length > 0 ? (
            <PanelCard title="Most Active Users (30d)" palette={palette} testId="team-analytics-active-users-card">
              {(enhanced.top_active_users || []).map((user: any, index: number) => (
                <View
                  key={user.user_id}
                  data-testid={`active-user-${index}`}
                  testID={`active-user-${index}`}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingVertical: 8,
                    borderBottomWidth: index < enhanced.top_active_users.length - 1 ? 1 : 0,
                    borderBottomColor: palette.border,
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: palette.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: palette.primary, fontSize: 10, fontWeight: '800' }}>#{index + 1}</Text>
                    </View>
                    <View>
                      <Text style={{ color: palette.text, fontSize: 12, fontWeight: '600' }}>{user.name}</Text>
                      <Text style={{ color: palette.textMuted, fontSize: 9 }}>{user.email}</Text>
                    </View>
                  </View>
                  <View style={{ backgroundColor: palette.primarySoft, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 }}>
                    <Text style={{ color: palette.primary, fontSize: 11, fontWeight: '800' }}>{user.actions}</Text>
                  </View>
                </View>
              ))}
            </PanelCard>
          ) : null}
        </View>
      )}

      {view === 'activity' && (
        <View>
          <PanelCard title="Activity Breakdown" palette={palette} testId="team-analytics-activity-breakdown-card">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {(data.activity_breakdown || []).map((activity: any) => (
                <View key={activity.action} style={{ flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: palette.cardAlt, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: palette.border }}>
                  <Ionicons name={(ACTION_ICONS[activity.action] || 'document-text') as any} size={12} color={palette.primary} />
                  <Text style={{ color: palette.text, fontSize: 10, fontWeight: '600' }}>{(activity.action || '').replace(/_/g, ' ')}</Text>
                  <View style={{ backgroundColor: palette.primarySoft, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4 }}>
                    <Text style={{ color: palette.primary, fontSize: 9, fontWeight: '800' }}>{activity.count}</Text>
                  </View>
                </View>
              ))}
            </View>
            {(data.activity_breakdown || []).length === 0 ? <EmptyMessage label="No activity yet" muted={palette.textMuted} /> : null}
          </PanelCard>

          {(enhanced?.activity_heatmap || []).length > 0 ? (
            <PanelCard title="Activity Heatmap (by hour)" palette={palette} testId="team-analytics-heatmap-card">
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 3 }}>
                {Array.from({ length: 24 }, (_, hour) => {
                  const entry = (enhanced.activity_heatmap || []).find((item: any) => item.hour === hour);
                  const count = entry?.count || 0;
                  const maxCount = Math.max(...(enhanced.activity_heatmap || []).map((item: any) => item.count), 1);
                  const intensity = count / maxCount;
                  const backgroundColor = intensity > 0.7 ? palette.primary : intensity > 0.2 ? palette.primarySoft : palette.cardAlt;
                  const textColor = intensity > 0.7 ? palette.primaryText : palette.textMuted;
                  return (
                    <View key={hour} data-testid={`heatmap-hour-${hour}`} testID={`heatmap-hour-${hour}`} style={{ width: 28, height: 28, borderRadius: 6, backgroundColor, alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ color: textColor, fontSize: 8, fontWeight: '700' }}>{hour}h</Text>
                      {count > 0 ? <Text style={{ color: textColor, opacity: 0.72, fontSize: 6 }}>{count}</Text> : null}
                    </View>
                  );
                })}
              </View>
            </PanelCard>
          ) : null}
        </View>
      )}
    </View>
  );
}

function PanelCard({ title, children, palette, testId }: { title: string; children: React.ReactNode; palette: any; testId: string }) {
  return (
    <View style={{ backgroundColor: palette.card, borderRadius: 12, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: palette.border }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.text, fontSize: 14, fontWeight: '700', marginBottom: 12 }}>{title}</Text>
      {children}
    </View>
  );
}

function KPI({ label, value, color, icon, textMuted }: any) {
  return (
    <View style={{ flex: 1, minWidth: 110, backgroundColor: `${color}08`, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: `${color}20` }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 6 }}>
        <Ionicons name={icon} size={13} color={color} />
        <Text style={{ color: textMuted, fontSize: 10, fontWeight: '600' }}>{label}</Text>
      </View>
      <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    </View>
  );
}

function EmptyMessage({ label, muted }: { label: string; muted: string }) {
  return <Text style={{ color: muted, fontSize: 11, textAlign: 'center', padding: 12 }}>{label}</Text>;
}