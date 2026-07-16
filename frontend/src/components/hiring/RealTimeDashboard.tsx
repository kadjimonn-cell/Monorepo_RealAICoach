import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';

type Props = { C: any; isWide: boolean };

export const RealTimeDashboard = ({ C, isWide }: Props) => {
  const [autoRefresh, setAutoRefresh] = useState(true);

  const { data: stats, loading } = useLiveQuery('/realtime/hiring-stats', { entity: 'hiring_stats', pollInterval: autoRefresh ? 15000 : 0 });

  if (loading) return (
    <View style={{ alignItems: 'center', paddingVertical: 40 }}>
      <ActivityIndicator size="large" color={C.accent} />
      <Text style={{ color: C.muted, marginTop: 12 }}>Loading real-time data...</Text>
    </View>
  );
  if (!stats) return null;

  const p = stats.pipelines || {};
  const iv = stats.interviews || {};
  const apps = stats.applications || {};
  const live = stats.live || {};

  return (
    <View data-testid="realtime-dashboard" testID="realtime-dashboard">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: autoRefresh ? C.success : C.muted }} />
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '700' }}>Real-Time Intelligence</Text>
        </View>
        <TouchableOpacity data-testid="toggle-auto-refresh" testID="toggle-auto-refresh" onPress={() => setAutoRefresh(!autoRefresh)}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 4, padding: 8, borderRadius: 8, backgroundColor: autoRefresh ? (globalThis as any).__alphaColor(C.success, '22') : C.border }}>
          <Ionicons name={autoRefresh ? 'pulse' : 'pause'} size={14} color={autoRefresh ? C.success : C.muted} />
          <Text style={{ color: autoRefresh ? C.success : C.muted, fontSize: 11, fontWeight: '600' }}>
            {autoRefresh ? 'Live' : 'Paused'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Live Counters Grid */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <StatCard icon="git-branch-outline" label="Active Pipelines" value={p.active} color={'var(--app-primary)'} C={C} />
        <StatCard icon="checkmark-done" label="Completed" value={p.completed} color={C.successText} C={C} />
        <StatCard icon="videocam-outline" label="Pending Interviews" value={iv.pending} color={C.primary} C={C} />
        <StatCard icon="today-outline" label="Today's Interviews" value={iv.today} color={C.warningText} C={C} />
        <StatCard icon="people-outline" label="New Apps (7d)" value={apps.new_this_week} color={'var(--app-primary)'} C={C} />
        <StatCard icon="briefcase-outline" label="Active Jobs" value={stats.jobs?.active} color={C.successText} C={C} />
        <StatCard icon="radio-outline" label="Live Video Rooms" value={live.active_video_rooms} color={C.error} C={C} />
        <StatCard icon="trending-up-outline" label="Recent Advances" value={live.recent_advances} color={'var(--app-warning)'} C={C} />
      </View>

      {/* Recent Pipeline Updates */}
      {(stats.recent_pipeline_updates || []).length > 0 && (
        <View style={{ backgroundColor: C.card, borderRadius: 12, padding: 16, borderWidth: 1, borderColor: C.border }}>
          <Text style={{ color: C.text, fontSize: 15, fontWeight: '700', marginBottom: 10 }}>Recent Pipeline Activity</Text>
          {stats.recent_pipeline_updates.map((u: any, i: number) => (
            <View key={i} style={{
              flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
              paddingVertical: 8, borderBottomWidth: i < stats.recent_pipeline_updates.length - 1 ? 1 : 0, borderBottomColor: C.border,
            }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: C.accent }} />
                <Text style={{ color: C.text, fontSize: 13 }}>{u.pipeline_id?.slice(0, 12)}...</Text>
              </View>
              <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.accent, '22'), paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 }}>
                <Text style={{ color: C.accent, fontSize: 11, fontWeight: '600' }}>
                  {(u.current_stage || '').replace(/_/g, ' ')}
                </Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {/* Refresh */}
      <TouchableOpacity data-testid="refresh-realtime" testID="refresh-realtime" onPress={load}
        style={{ marginTop: 12, padding: 12, borderRadius: 10, backgroundColor: C.border, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
        <Ionicons name="refresh" size={16} color={C.text} />
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '600' }}>Refresh Now</Text>
      </TouchableOpacity>
    </View>
  );
};

const StatCard = ({ icon, label, value, color, C }: { icon: string; label: string; value: any; color: string; C: any }) => (
  <View style={{
    backgroundColor: C.card, borderRadius: 12, padding: 14, minWidth: 140, flex: 1,
    borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: color,
  }}>
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
      <Ionicons name={icon as any} size={16} color={color} />
      <Text style={{ color: C.muted, fontSize: 11 }}>{label}</Text>
    </View>
    <Text style={{ color: C.text, fontSize: 24, fontWeight: '700' }}>{value ?? 0}</Text>
  </View>
);

/* i18n-probe t('i18n.auto.probe') */
