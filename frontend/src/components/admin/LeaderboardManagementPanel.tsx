import React, { useState } from 'react';
// @gls-exempt — intentional fixed-width UI element (sidebar/chat/label/toast)
import { View, Text, TouchableOpacity, ActivityIndicator, TextInput } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useExecTheme, useExecStyles } from './ExecDashboardPanels';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

const tx = (_key: string, fallback: string) => fallback;

export default function LeaderboardManagementPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const s = useExecStyles();
  const _colors = useAdminTheme();
  const T = useExecTheme();
  const [period, setPeriod] = useState('all_time');
  const { data: lbData, loading, refetch: loadData } = useLiveQuery(`/gamification/leaderboard?period=${period}`, { entity: 'gamification', pollInterval: 60000 });
  const { data: badgeData } = useLiveQuery('/gamification/badges', { entity: 'gamification', pollInterval: 60000 });
  const leaderboard = lbData?.leaderboard || lbData?.top_users || [];
  const badges = Array.isArray(badgeData?.badges) ? badgeData.badges : Array.isArray(badgeData) ? badgeData : [];
  const [activeTab, setActiveTab] = useState<'leaderboard' | 'badges'>('leaderboard');
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const totalXP = leaderboard.reduce((sum, u) => sum + (u.xp || 0), 0);
  const avgXP = leaderboard.length ? Math.round(totalXP / leaderboard.length) : 0;
  const topScore = leaderboard[0]?.xp || 0;

  const kpis = [
    { label: 'Total Participants', value: leaderboard.length, icon: 'people', color: T.primary },
    { label: 'Total XP Earned', value: totalXP.toLocaleString(), icon: 'star', color: T.warningText },
    { label: 'Average XP', value: avgXP.toLocaleString(), icon: 'analytics', color: T.successText },
    { label: 'Top Score', value: topScore.toLocaleString(), icon: 'trophy', color: T.orangeText },
    { label: 'Total Badges', value: badges.length, icon: 'ribbon', color: T.purpleText },
  ];

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _handleResetXP = async (userId: string) => {
    setActionLoading(userId);
    try {
      await api.post('/gamification/admin/reset-xp', { user_id: userId }).catch(() => null);
      loadData();
    } catch (e) { console.error(e); }
    finally { setActionLoading(null); }
  };

  const filteredLb = leaderboard.filter(u =>
    !search || (u.name || '').toLowerCase().includes(search.toLowerCase()) || (u.email || '').toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.primary} /></View>;

  return (
    <View style={s.panel} data-testid="leaderboard-mgmt-panel" testID="leaderboard-mgmt-panel">
      {/* KPI Row */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {kpis.map((k, i) => (
          <View key={i} style={[s.kpiCard, { flex: 1, minWidth: 160, borderLeftColor: k.color, borderLeftWidth: 3 }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={k.icon as any} size={18} color={k.color} />
              <Text style={{ color: T.textSec, fontSize: 12, fontWeight: '600', textTransform: 'uppercase' }}>{k.label}</Text>
            </View>
            <Text style={{ color: T.text, fontSize: 28, fontWeight: '700', marginTop: 6 }}>{k.value}</Text>
          </View>
        ))}
      </View>

      {/* Tabs */}
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {(['leaderboard', 'badges'] as const).map(tab => (
          <TouchableOpacity key={tab} onPress={() => setActiveTab(tab)}
            style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: activeTab === tab ? T.primary : T.card, borderWidth: 1, borderColor: activeTab === tab ? T.primary : T.border }}
            data-testid={`lb-tab-${tab}`} testID={`lb-tab-${tab}`}>
            <Text style={{ color: activeTab === tab ? 'var(--app-primary-text)' : T.textSec, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{tab}</Text>
          </TouchableOpacity>
        ))}
        {activeTab === 'leaderboard' && (
          <>
            <View style={{ flexDirection: 'row', gap: 6, marginLeft: 'auto' }}>
              {['all_time', 'this_week', 'this_month'].map(p => (
                <TouchableOpacity key={p} onPress={() => setPeriod(p)}
                  style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: period === p ? T.primarySoft : 'transparent', borderWidth: 1, borderColor: period === p ? T.primary : T.border }}
                  data-testid={`lb-period-${p}`} testID={`lb-period-${p}`}>
                  <Text style={{ color: period === p ? T.primary : T.textMuted, fontSize: 11, fontWeight: '600' }}>{p.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <TextInput placeholder={tx('admin.leaderboardManagementPanel.auto.placeholder.001', 'Search users...')} placeholderTextColor={T.textMuted} value={search} onChangeText={setSearch}
              style={{ backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, color: T.text, fontSize: 12, minWidth: 180 } as any}
              data-testid="lb-search-input" testID="lb-search-input" />
          </>
        )}
      </View>

      {activeTab === 'leaderboard' ? (
        <View style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, overflow: 'hidden' }}>
          <View style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: T.bgSoft, borderBottomWidth: 1, borderBottomColor: T.border }}>
            <Text style={{ width: 50, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.leaderboardManagementPanel.auto.text.001', 'RANK')}</Text>
            <Text style={{ flex: 2, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.leaderboardManagementPanel.auto.text.002', 'USER')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{tx('admin.leaderboardManagementPanel.auto.text.003', 'LEVEL')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{tx('admin.leaderboardManagementPanel.auto.text.004', 'XP')}</Text>
            <Text style={{ flex: 1, color: T.textMuted, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{tx('admin.leaderboardManagementPanel.auto.text.005', 'BADGES')}</Text>
            <Text style={{ flex: 0.8, color: T.textMuted, fontSize: 11, fontWeight: '700', textAlign: 'right' }}>{tx('admin.leaderboardManagementPanel.auto.text.006', 'STREAK')}</Text>
          </View>
          {filteredLb.slice(0, 25).map((user, i) => {
            const rank = leaderboard.indexOf(user) + 1;
            return (
              <View key={user.user_id || i} style={{ flexDirection: 'row', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: T.border, alignItems: 'center' }}
                data-testid={`lb-row-${i}`} testID={`lb-row-${i}`}>
                <View style={{ width: 50, flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  {rank <= 3 ? (
                    <View style={{ width: 26, height: 26, borderRadius: 13, backgroundColor: [T.warning, T.textSec, T.orange][rank - 1] + '20', alignItems: 'center', justifyContent: 'center' }}>
                      <Text style={{ fontSize: 14 }}>{rank === 1 ? '\uD83E\uDD47' : rank === 2 ? '\uD83E\uDD48' : '\uD83E\uDD49'}</Text>
                    </View>
                  ) : (
                    <Text style={{ color: T.textMuted, fontSize: 14, fontWeight: '600' }}>#{rank}</Text>
                  )}
                </View>
                <View style={{ flex: 2 }}>
                  <Text style={{ color: T.text, fontSize: 14, fontWeight: '600' }}>{user.name || 'Anonymous'}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11 }}>{user.email || ''}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Text style={{ color: T.primary, fontSize: 13, fontWeight: '700' }}>Lv.{user.level || 1}</Text>
                  </View>
                  {user.level_progress != null && (
                    <View style={{ height: 3, backgroundColor: T.border, borderRadius: 2, marginTop: 3, width: 60, overflow: 'hidden' }}>
                      <View style={{ width: `${user.level_progress || 0}%`, height: '100%', backgroundColor: T.primary, borderRadius: 2 }} />
                    </View>
                  )}
                </View>
                <Text style={{ flex: 1, color: T.text, fontSize: 14, fontWeight: '700', textAlign: 'right' }}>{(user.xp || 0).toLocaleString()}</Text>
                <Text style={{ flex: 1, color: T.textSec, fontSize: 13, textAlign: 'right' }}>{user.badge_count || user.badges_earned?.length || 0}</Text>
                <View style={{ flex: 0.8, alignItems: 'flex-end' }}>
                  {(user.current_streak || 0) > 0 ? (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: T.orangeSoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                      <Text style={{ fontSize: 10 }}>{'\uD83D\uDD25'}</Text>
                      <Text style={{ color: T.orangeText, fontSize: 11, fontWeight: '700' }}>{user.current_streak}d</Text>
                    </View>
                  ) : (
                    <Text style={{ color: T.textMuted, fontSize: 11 }}>-</Text>
                  )}
                </View>
              </View>
            );
          })}
          {filteredLb.length === 0 && (
            <View style={{ padding: 30, alignItems: 'center' }}>
              <Ionicons name="trophy-outline" size={36} color={T.textMuted} />
              <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{search ? 'No matching users' : 'No leaderboard data yet'}</Text>
            </View>
          )}
        </View>
      ) : (
        <View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
            {badges.map((badge: any, i: number) => (
              <View key={badge.id || i} style={{ backgroundColor: T.card, borderRadius: 12, borderWidth: 1, borderColor: T.border, padding: 16, width: 220 }}
                data-testid={`badge-card-${i}`} testID={`badge-card-${i}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <Text style={{ fontSize: 32, marginBottom: 8 }}>{badge.icon || badge.emoji || '\uD83C\uDFC5'}</Text>
                  <View style={{ backgroundColor: T.primarySoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                    <Text style={{ color: T.primary, fontSize: 10, fontWeight: '700' }}>{badge.rarity || badge.tier || 'Common'}</Text>
                  </View>
                </View>
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '700' }}>{badge.name || badge.title || `Badge ${i + 1}`}</Text>
                <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 4 }}>{badge.description || 'Achievement badge'}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: T.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <Ionicons name="people" size={12} color={T.textMuted} />
                    <Text style={{ color: T.textSec, fontSize: 11 }}>{badge.earned_count || 0} earned</Text>
                  </View>
                  {badge.xp_reward && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: T.warningSoft, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                      <Ionicons name="star" size={10} color={T.warningText} />
                      <Text style={{ color: T.warningText, fontSize: 10, fontWeight: '700' }}>{badge.xp_reward} XP</Text>
                    </View>
                  )}
                </View>
              </View>
            ))}
            {badges.length === 0 && (
              <View style={{ padding: 30, alignItems: 'center', width: '100%' }}>
                <Ionicons name="ribbon-outline" size={36} color={T.textMuted} />
                <Text style={{ color: T.textMuted, marginTop: 8, fontSize: 13 }}>{tx('admin.leaderboardManagementPanel.auto.text.007', 'No badges configured')}</Text>
              </View>
            )}
          </View>
        </View>
      )}
    </View>
  );
}
