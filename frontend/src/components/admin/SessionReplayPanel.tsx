import React, { useEffect, useState, useCallback, useRef } from 'react';
import { View, Text, ScrollView, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const _AC = {
  bg: 'var(--app-bg)' as any, bgAlt: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any, surface: 'var(--app-surface)' as any, surfaceHover: 'var(--app-surface-hover)' as any, border: 'var(--app-border)' as any, borderStrong: 'var(--app-border-strong)' as any,
  text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any, textDim: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
};
interface Props { colors: any; }

function makeT(AC: any) { return {
  bg: 'var(--app-bg)', card: AC.surface, border: 'var(--app-border)',
  text: AC.text, textSec: AC.textMuted, textMuted: AC.textDim,
  highlight: 'var(--app-primary)',
}; }

const tx = (_key: string, fallback: string) => fallback;

const EVENT_ICONS: Record<string, string> = {
  click: 'finger-print', navigate: 'navigate', scroll: 'swap-vertical', input: 'create',
};

export default function SessionReplayPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const [tab, setTab] = useState<'sessions' | 'replay' | 'stats'>('sessions');
  const [selectedSession, setSelectedSession] = useState<any>(null);
  const [replayEvents, setReplayEvents] = useState<any[]>([]);
  const [replayIndex, setReplayIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [page, setPage] = useState(1);
  const timerRef = useRef<any>(null);
  const PAGE_SIZE = 20;

  const { data: sessionsData, loading: sessionsLoading, refetch: refetchSessions, lastUpdated } = useLiveQuery(`/admin/session-replay/sessions?page=${page}&limit=${PAGE_SIZE}&days=7`, { entity: 'session_replay', pollInterval: 30000 });
  const { data: statsData } = useLiveQuery('/admin/session-replay/stats?days=7', { entity: 'session_replay', pollInterval: 60000 });

  const sessions = sessionsData?.sessions || [];
  const total = sessionsData?.total || 0;
  const stats = statsData || null;
  const loading = sessionsLoading;

  const loadReplay = useCallback(async (sessionId: string) => {
    try {
      const res = await api.get(`/admin/session-replay/sessions/${sessionId}`);
      setSelectedSession(res.data.session);
      setReplayEvents(res.data.events || []);
      setReplayIndex(0);
      setPlaying(false);
      setTab('replay');
    } catch { /* skip */ }
  }, []);

  // Replay playback
  useEffect(() => {
    if (playing && replayIndex < replayEvents.length - 1) {
      timerRef.current = setTimeout(() => {
        setReplayIndex(prev => prev + 1);
      }, 500);
    } else if (replayIndex >= replayEvents.length - 1) {
      setPlaying(false);
    }
    return () => clearTimeout(timerRef.current);
  }, [playing, replayIndex, replayEvents.length]);

  const togglePlay = () => {
    if (replayIndex >= replayEvents.length - 1) setReplayIndex(0);
    setPlaying(!playing);
  };

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.highlight} /></View>;
      // eslint-disable-next-line no-unused-expressions
      <AutoFixBanner domain="session_replay" />

  const tabs = [
    { id: 'sessions', label: 'Sessions', icon: 'list' },
    { id: 'replay', label: 'Replay', icon: 'play-circle' },
    { id: 'stats', label: 'Statistics', icon: 'stats-chart' },
  ] as const;

  const fmtDuration = (s: number) => {
    if (s < 60) return `${s}s`;
    return `${Math.floor(s / 60)}m ${s % 60}s`;
  };

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="replay-title" testID="replay-title">{tx('admin.sessionReplayPanel.auto.text.001', 'Session Replay')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 2 }}>{tx('admin.sessionReplayPanel.auto.text.002', 'Review user sessions and interaction patterns')}</Text>
        </View>
        <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={refetchSessions} isRefreshing={loading} accentColor={T.highlight} textColor={T.textMuted} />
      </View>

      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 20 }} data-testid="replay-tabs" testID="replay-tabs">
        {tabs.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setTab(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: tab === t.id ? T.highlight : T.card, borderWidth: 1, borderColor: tab === t.id ? T.highlight : T.border }}
            data-testid={`replay-tab-${t.id}`} testID={`replay-tab-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={tab === t.id ? 'var(--app-primary-text)' : T.textMuted} />
            <Text style={{ fontSize: 12, fontWeight: '700', color: tab === t.id ? 'var(--app-primary-text)' : T.textSec }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Sessions List */}
      {tab === 'sessions' && (
        <View data-testid="replay-sessions-list" testID="replay-sessions-list">
          <Text style={{ fontSize: 11, color: T.textMuted, marginBottom: 10 }}>{total} sessions recorded (7d)</Text>
          {sessions.length === 0 && (
            <View style={{ padding: 40, alignItems: 'center', backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="videocam-off" size={32} color={T.textMuted} />
              <Text style={{ fontSize: 13, color: T.textMuted, marginTop: 8 }}>{tx('admin.sessionReplayPanel.auto.text.003', 'No session recordings yet')}</Text>
              <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 4, textAlign: 'center' }}>{tx('admin.sessionReplayPanel.auto.text.004', 'Sessions will be recorded as users interact with the platform.')}</Text>
            </View>
          )}
          {sessions.map((s, i) => (
            <TouchableOpacity key={i} onPress={() => loadReplay(s.session_id)}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12, paddingHorizontal: 14, backgroundColor: T.card, borderRadius: 12, marginBottom: 6, borderWidth: 1, borderColor: T.border }}
              data-testid={`replay-session-${i}`} testID={`replay-session-${i}`}>
              <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.highlight, '15'), alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name="person" size={16} color={T.highlight} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: T.text }}>{s.user_email || s.user_id?.slice(0, 16)}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>{s.event_count || 0} events | {fmtDuration(s.duration_seconds || 0)} | {s.status || 'active'}</Text>
              </View>
              <Text style={{ fontSize: 10, color: T.textMuted }}>{s.started_at?.slice(0, 16).replace('T', ' ')}</Text>
              <Ionicons name="play-circle" size={18} color={T.highlight} />
            </TouchableOpacity>
          ))}
          {total > PAGE_SIZE && (
            <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 10, marginTop: 12 }}>
              <TouchableOpacity
                disabled={page <= 1}
                accessibilityLabel={tx('admin.sessionReplayPanel.auto.accessibility.001', 'Previous page')}
                onPress={() => setPage(p => Math.max(1, p - 1))}
                data-testid="session-replay-prev-page"
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, opacity: page <= 1 ? 0.4 : 1 }}>
                <Text style={{ fontSize: 11, color: T.textSec }}>{tx('admin.sessionReplayPanel.auto.text.005', 'Prev')}</Text>
              </TouchableOpacity>
              <Text style={{ fontSize: 11, color: T.textMuted, minWidth: 80, textAlign: 'center' }} data-testid="session-replay-page-indicator">
                Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}
              </Text>
              <TouchableOpacity
                disabled={page >= Math.ceil(total / PAGE_SIZE)}
                accessibilityLabel={tx('admin.sessionReplayPanel.auto.accessibility.002', 'Next page')}
                onPress={() => setPage(p => p + 1)}
                data-testid="session-replay-next-page"
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 8, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, opacity: page >= Math.ceil(total / PAGE_SIZE) ? 0.4 : 1 }}>
                <Text style={{ fontSize: 11, color: T.textSec }}>{tx('admin.sessionReplayPanel.auto.text.006', 'Next')}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* Replay View */}
      {tab === 'replay' && (
        <View data-testid="replay-player" testID="replay-player">
          {!selectedSession ? (
            <View style={{ padding: 40, alignItems: 'center', backgroundColor: T.card, borderRadius: 14, borderWidth: 1, borderColor: T.border }}>
              <Ionicons name="play-circle" size={40} color={T.textMuted} />
              <Text style={{ fontSize: 14, color: T.textMuted, marginTop: 10, fontWeight: '600' }}>{tx('admin.sessionReplayPanel.auto.text.007', 'Select a session to replay')}</Text>
              <TouchableOpacity accessibilityLabel={tx('admin.sessionReplayPanel.auto.accessibility.003', 'Browse Sessions')} onPress={() => setTab('sessions')} style={{ marginTop: 12, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 8, backgroundColor: T.highlight }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: colors.primaryText }}>{tx('admin.sessionReplayPanel.auto.text.008', 'Browse Sessions')}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View>
              {/* Session Info */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border, marginBottom: 14 }}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <View>
                    <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{selectedSession.user_email}</Text>
                    <Text style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>
                      {selectedSession.started_at?.slice(0, 19).replace('T', ' ')} | {fmtDuration(selectedSession.duration_seconds || 0)} | {selectedSession.event_count} events
                    </Text>
                  </View>
                  <TouchableOpacity accessibilityLabel={tx('admin.sessionReplayPanel.auto.accessibility.004', 'close button')} onPress={() => { setSelectedSession(null); setTab('sessions'); }}
                    style={{ padding: 6, borderRadius: 8, backgroundColor: T.border }}>
                    <Ionicons name="close" size={14} color={T.textSec} />
                  </TouchableOpacity>
                </View>
              </View>

              {/* Playback Controls */}
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <TouchableOpacity onPress={togglePlay} style={{ width: 40, height: 40, borderRadius: 20, backgroundColor: T.highlight, alignItems: 'center', justifyContent: 'center' }} data-testid="replay-play-btn" testID="replay-play-btn">
                  <Ionicons name={playing ? 'pause' : 'play'} size={18} color="var(--app-primary-text)" />
                </TouchableOpacity>
                <View style={{ flex: 1, height: 6, borderRadius: 3, backgroundColor: T.border }}>
                  <View style={{ width: `${replayEvents.length > 0 ? (replayIndex / replayEvents.length) * 100 : 0}%`, height: 6, borderRadius: 3, backgroundColor: T.highlight }} />
                </View>
                <Text style={{ fontSize: 11, fontWeight: '700', color: T.textSec }}>{replayIndex + 1}/{replayEvents.length}</Text>
              </View>

              {/* Event Timeline */}
              <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: T.text, marginBottom: 10 }}>{tx('admin.sessionReplayPanel.auto.text.009', 'Event Timeline')}</Text>
                {replayEvents.length === 0 && (
                  <Text style={{ fontSize: 12, color: T.textMuted, textAlign: 'center', paddingVertical: 20 }}>{tx('admin.sessionReplayPanel.auto.text.010', 'No events recorded for this session')}</Text>
                )}
                {replayEvents.slice(Math.max(0, replayIndex - 5), replayIndex + 10).map((e, i) => {
                  const actualIdx = Math.max(0, replayIndex - 5) + i;
                  const isCurrent = actualIdx === replayIndex;
                  const isPast = actualIdx < replayIndex;
                  return (
                    <TouchableOpacity key={i} accessibilityLabel={tx('admin.sessionReplayPanel.auto.accessibility.005', 'e.type')} onPress={() => setReplayIndex(actualIdx)}
                      style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 8, marginBottom: 2, backgroundColor: isCurrent ? (globalThis as any).__alphaColor(T.highlight, '15') : 'transparent', borderWidth: 1, borderColor: isCurrent ? (globalThis as any).__alphaColor(T.highlight, '40') : 'transparent' }}>
                      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: isCurrent ? T.highlight : isPast ? T.textMuted : T.border }} />
                      <View style={{ width: 24, height: 24, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor((isCurrent ? T.highlight : T.textMuted), '15'), alignItems: 'center', justifyContent: 'center' }}>
                        <Ionicons name={(EVENT_ICONS[e.type] || 'ellipse') as any} size={11} color={isCurrent ? T.highlight : T.textMuted} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 11, fontWeight: '600', color: isCurrent ? T.text : T.textSec }}>{e.type}</Text>
                        <Text style={{ fontSize: 9, color: T.textMuted }} numberOfLines={1}>{e.data?.url || e.data?.element || e.data?.page || ''}</Text>
                      </View>
                      <Text style={{ fontSize: 9, color: T.textMuted }}>{e.timestamp?.slice(11, 19)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          )}
        </View>
      )}

      {/* Statistics */}
      {tab === 'stats' && stats && (
        <View data-testid="replay-stats" testID="replay-stats">
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'Total Sessions', value: stats.total_sessions, icon: 'videocam', color: colors.primary },
              { label: 'Unique Users', value: stats.unique_users, icon: 'people', color: colors.accent },
              { label: 'Avg Duration', value: fmtDuration(stats.avg_duration_seconds || 0), icon: 'time', color: colors.warningText },
            ].map(k => (
              <View key={k.label} style={{ flex: 1, minWidth: 140, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
                <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(k.color, '15'), alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
                  <Ionicons name={k.icon as any} size={16} color={k.color} />
                </View>
                <Text style={{ fontSize: 22, fontWeight: '800', color: T.text }}>{typeof k.value === 'number' ? k.value.toLocaleString() : k.value}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 2 }}>{k.label}</Text>
              </View>
            ))}
          </View>

          {stats.top_pages?.length > 0 && (
            <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text, marginBottom: 12 }}>{tx('admin.sessionReplayPanel.auto.text.011', 'Most Visited Pages')}</Text>
              {stats.top_pages.map((p: any, i: number) => {
                const maxVisits = stats.top_pages[0]?.visits || 1;
                return (
                  <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    <Text style={{ width: 20, fontSize: 11, fontWeight: '800', color: i < 3 ? 'var(--app-warning)' : T.textMuted, textAlign: 'center' }}>#{i + 1}</Text>
                    <View style={{ flex: 1 }}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
                        <Text style={{ fontSize: 12, fontWeight: '600', color: T.text }} numberOfLines={1}>{p.page || 'Unknown'}</Text>
                        <Text style={{ fontSize: 11, color: T.textSec }}>{p.visits} visits</Text>
                      </View>
                      <View style={{ height: 6, borderRadius: 3, backgroundColor: T.border }}>
                        <View style={{ width: `${(p.visits / maxVisits) * 100}%`, height: 6, borderRadius: 3, backgroundColor: T.highlight }} />
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}
