import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useLanguage } from '../../i18n/LanguageContext';
import FpsArena from './FpsArena';

type RoomRow = { room_id: string; name: string; players: number; max_players: number };
type LeaderRow = { rank: number; display_name: string; kills: number; deaths: number; kd_ratio: number; matches_played: number };
type MatchRow = { match_id: string; room_id: string; kills: number; deaths: number; won: boolean; best_streak?: number; created_at: string };

type ArenaSession = { roomId: string; roomName: string; playerName: string; model: string };

const MODEL_META: Record<string, { color: string; icon: string }> = {
  policeman: { color: '#eab308' /* @theme-ok brand-fixed-palette */, icon: 'shield-outline' },
  robotx: { color: '#db2777' /* @theme-ok brand-fixed-palette */, icon: 'hardware-chip-outline' },
  roboty: { color: '#3b82f6' /* @theme-ok brand-fixed-palette */, icon: 'hardware-chip-outline' },
};

export default function FpsGameHub() {
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [bootstrap, setBootstrap] = useState<any>(null);
  const [playerName, setPlayerName] = useState('');
  const [roomName, setRoomName] = useState('');
  const [model, setModel] = useState('policeman');
  const [joining, setJoining] = useState(false);
  const [session, setSession] = useState<ArenaSession | null>(null);
  const [invited, setInvited] = useState(false);
  const [inviteCopied, setInviteCopied] = useState(false);
  const [matches, setMatches] = useState<MatchRow[]>([]);
  const [sharedMatchId, setSharedMatchId] = useState('');

  const shareMatch = useCallback(async (m: MatchRow) => {
    if (typeof window === 'undefined') return;
    const url = `${window.location.origin}/fps-match/${encodeURIComponent(m.match_id)}`;
    const text = tx('fpsGame.recent.shareMessage', 'Check out my FPS match result on RealAICoach!');
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: tx('fpsMatch.title', 'FPS Match Card'), text, url });
        return;
      } catch { /* dismissed — fall through to clipboard */ }
    }
    navigator.clipboard?.writeText(url).then(() => {
      setSharedMatchId(m.match_id);
      setTimeout(() => setSharedMatchId(''), 2500);
    }).catch(() => { /* clipboard unavailable */ });
  }, [tx]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const room = new URLSearchParams(window.location.search).get('room');
    if (room) {
      setRoomName(room.slice(0, 48));
      setInvited(true);
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    let ref = '';
    try { ref = window.localStorage?.getItem('fps_share_ref') || ''; } catch { /* storage unavailable */ }
    if (!ref) return;
    try { window.localStorage?.removeItem('fps_share_ref'); } catch { /* ignore */ }
    api.post('/games-station/share-join', { match_id: ref }).catch(() => { /* attribution is best-effort */ });
  }, []);

  const copyInvite = useCallback(() => {
    const room = roomName.trim();
    if (!room) {
      setError(tx('fpsGame.errors.roomRequired', 'Enter a room name to join or create a room.'));
      return;
    }
    navigator.clipboard?.writeText(`${window.location.origin}/features/fps-game?room=${encodeURIComponent(room)}`).then(() => {
      setInviteCopied(true);
      setTimeout(() => setInviteCopied(false), 2500);
    }).catch(() => { /* clipboard unavailable */ });
  }, [roomName, tx]);

  const loadBootstrap = useCallback(async () => {
    try {
      setError('');
      const resp = await api.get('/games-station/bootstrap');
      setBootstrap(resp.data);
      const profile = resp.data?.profile || {};
      setPlayerName((prev) => prev || String(profile.display_name || user?.name || ''));
      setModel(String(profile.preferred_model || 'policeman'));
      try {
        const hist = await api.get('/games-station/match-history?limit=5');
        setMatches(hist.data?.matches || []);
      } catch { /* history optional */ }
    } catch (err: any) {
      setError(String(err?.response?.data?.detail || err?.message || tx('fpsGame.errors.loadFailed', 'Unable to load FPS Game.')));
    } finally {
      setLoading(false);
    }
  }, [tx, user?.name]);

  useEffect(() => { loadBootstrap(); }, [loadBootstrap]);

  const joinRoom = useCallback(async (targetRoom?: string) => {
    const finalRoom = String(targetRoom || roomName).trim();
    if (!finalRoom) {
      setError(tx('fpsGame.errors.roomRequired', 'Enter a room name to join or create a room.'));
      return;
    }
    setJoining(true);
    setError('');
    try {
      const resp = await api.post('/games-station/rooms/join', {
        room_name: finalRoom,
        player_name: playerName.trim(),
        model,
      });
      setSession({
        roomId: String(resp.data.room_id),
        roomName: String(resp.data.room_name),
        playerName: String(resp.data.player_name),
        model: String(resp.data.model),
      });
    } catch (err: any) {
      setError(String(err?.response?.data?.detail || err?.message || tx('fpsGame.errors.joinFailed', 'Unable to join the room.')));
    } finally {
      setJoining(false);
    }
  }, [roomName, playerName, model, tx]);

  const exitArena = useCallback(() => {
    setSession(null);
    loadBootstrap();
  }, [loadBootstrap]);

  if (session && user?.user_id) {
    return (
      <FpsArena
        roomId={session.roomId}
        roomName={session.roomName}
        userId={user.user_id}
        playerName={session.playerName}
        model={session.model}
        onExit={exitArena}
      />
    );
  }

  if (loading) {
    return (
      <View style={[styles.center, { paddingVertical: 60 }]} data-testid="fps-game-loading" testID="fps-game-loading">
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const quota = bootstrap?.quota || {};
  const rooms: RoomRow[] = bootstrap?.rooms || [];
  const leaderboard: LeaderRow[] = bootstrap?.leaderboard || [];
  const cardBg = darkMode ? 'rgba(255,255,255,0.04)' : '#ffffff';
  const border = darkMode ? 'rgba(255,255,255,0.09)' : 'rgba(15,23,42,0.10)';
  const subText = darkMode ? 'rgba(226,232,240,0.72)' : 'rgba(15,23,42,0.62)';

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 48 }} data-testid="fps-game-hub" testID="fps-game-hub">
      {!!error && (
        <View style={[styles.errorBanner, { borderColor: colors.error }]} data-testid="fps-game-error" testID="fps-game-error">
          <Ionicons name="warning-outline" size={16} color="#ef4444" />
          <Text style={{ color: colors.error, flex: 1 }}>{error}</Text>
        </View>
      )}

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="fps-game-lobby-card" testID="fps-game-lobby-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('fpsGame.lobby.title', 'Join the battle')}</Text>
        <Text style={{ color: subText, marginBottom: 14 }}>
          {tx('fpsGame.lobby.subtitle', 'Enter your player name and a room name, then join or create a room. Up to 8 players per room.')}
        </Text>
        {invited && (
          <View style={[styles.invitedBanner, { borderColor: colors.primary }]} data-testid="fps-game-invited-banner" testID="fps-game-invited-banner">
            <Ionicons name="mail-open-outline" size={15} color={colors.primary} />
            <Text style={{ color: colors.primary, flex: 1, fontSize: 13 }}>
              {tx('fpsGame.lobby.inviteHint', 'Invited by a friend? The room is pre-filled — just hit Join.')}
            </Text>
          </View>
        )}

        <Text style={[styles.label, { color: subText }]}>{tx('fpsGame.lobby.playerName', 'Player name')}</Text>
        <TextInput
          value={playerName}
          onChangeText={setPlayerName}
          maxLength={32}
          placeholder={tx('fpsGame.lobby.playerNamePlaceholder', 'Your call sign')}
          placeholderTextColor={subText}
          style={[styles.input, { color: colors.text, borderColor: border }]}
          data-testid="fps-game-player-name-input" testID="fps-game-player-name-input"
        />

        <Text style={[styles.label, { color: subText }]}>{tx('fpsGame.lobby.roomName', 'Room name')}</Text>
        <TextInput
          value={roomName}
          onChangeText={setRoomName}
          maxLength={48}
          placeholder={tx('fpsGame.lobby.roomNamePlaceholder', 'e.g. alpha-base')}
          placeholderTextColor={subText}
          style={[styles.input, { color: colors.text, borderColor: border }]}
          data-testid="fps-game-room-name-input" testID="fps-game-room-name-input"
        />

        <Text style={[styles.label, { color: subText }]}>{tx('fpsGame.lobby.model', 'Player model')}</Text>
        <View style={styles.modelRow}>
          {Object.keys(MODEL_META).map((key) => {
            const meta = MODEL_META[key];
            const active = model === key;
            return (
              <Pressable
                key={key}
                onPress={() => setModel(key)}
                style={[styles.modelCard, { borderColor: active ? meta.color : border, backgroundColor: active ? `${meta.color}22` : 'transparent' }]}
                data-testid={`fps-game-model-${key}`} testID={`fps-game-model-${key}`}
              >
                <Ionicons name={meta.icon as any} size={20} color={meta.color} />
                <Text style={{ color: colors.text, fontWeight: active ? '700' : '500', fontSize: 13 }}>
                  {key === 'policeman' ? tx('fpsGame.models.policeman', 'Policeman') : key === 'robotx' ? tx('fpsGame.models.robotx', 'Robot X') : tx('fpsGame.models.roboty', 'Robot Y')}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <View style={styles.actionRow}>
          <Pressable
            onPress={() => joinRoom()}
            disabled={joining}
            style={[styles.joinBtn, { backgroundColor: colors.primary, opacity: joining ? 0.6 : 1, flex: 1 }]}
            data-testid="fps-game-join-room-button" testID="fps-game-join-room-button"
          >
            {joining ? <ActivityIndicator size="small" color={colors.primaryText || '#fff'} /> : <Ionicons name="rocket-outline" size={18} color={colors.primaryText || '#fff'} />}
            <Text style={[styles.joinBtnText, { color: colors.primaryText || '#fff' }]}>{tx('fpsGame.lobby.joinOrCreate', 'Join or Create Room')}</Text>
          </Pressable>
          <Pressable
            onPress={copyInvite}
            style={[styles.inviteBtn, { borderColor: colors.primary }]}
            data-testid="fps-game-invite-button" testID="fps-game-invite-button"
          >
            <Ionicons name="link-outline" size={16} color={colors.primary} />
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 13 }}>
              {inviteCopied ? tx('fpsGame.lobby.inviteCopied', 'Invite link copied — send it to a friend!') : tx('fpsGame.lobby.invite', 'Copy invite link')}
            </Text>
          </Pressable>
        </View>

        <Text style={{ color: subText, fontSize: 12, marginTop: 10 }} data-testid="fps-game-quota-info" testID="fps-game-quota-info">
          {tx('fpsGame.lobby.plan', 'Plan')}: {String(quota.plan || 'free').toUpperCase()} · {tx('fpsGame.lobby.playsRemaining', 'Plays remaining today')}: {quota.daily_gameplay_limit === -1 ? tx('fpsGame.lobby.unlimited', 'Unlimited') : String(quota.daily_plays_remaining ?? '-')}
        </Text>
        {Number(bootstrap?.share_joins || 0) > 0 && (
          <View style={styles.shareJoinsChip} data-testid="fps-game-share-joins-chip" testID="fps-game-share-joins-chip">
            <Ionicons name="people-outline" size={14} color="#22c55e" />
            <Text style={{ color: colors.success, fontSize: 12, fontWeight: '700' }}>
              {bootstrap.share_joins} {tx('fpsGame.lobby.shareJoins', 'players joined from your shares')}
            </Text>
          </View>
        )}
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="fps-game-rooms-card" testID="fps-game-rooms-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('fpsGame.rooms.title', 'Active rooms')}</Text>
        {rooms.length === 0 ? (
          <Text style={{ color: subText }}>{tx('fpsGame.rooms.empty', 'No live rooms right now — create one above and invite a friend.')}</Text>
        ) : rooms.map((room) => (
          <View key={room.room_id} style={[styles.roomRow, { borderColor: border }]}>
            <Ionicons name="people-outline" size={16} color={colors.primary} />
            <Text style={{ color: colors.text, flex: 1, fontWeight: '600' }}>{room.name}</Text>
            <Text style={{ color: subText, fontSize: 12 }}>{room.players}/{room.max_players}</Text>
            <Pressable
              onPress={() => joinRoom(room.name)}
              style={[styles.smallBtn, { borderColor: colors.primary }]}
              data-testid={`fps-game-join-room-${room.room_id}`} testID={`fps-game-join-room-${room.room_id}`}
            >
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>{tx('fpsGame.rooms.join', 'Join')}</Text>
            </Pressable>
          </View>
        ))}
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="fps-game-recent-card" testID="fps-game-recent-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('fpsGame.recent.title', 'Recent matches')}</Text>
        {matches.length === 0 ? (
          <Text style={{ color: subText }}>{tx('fpsGame.recent.empty', 'No matches yet — play a round to earn a shareable match card.')}</Text>
        ) : matches.map((m) => (
          <View key={m.match_id} style={[styles.roomRow, { borderColor: border }]}>
            <Ionicons name={m.won ? 'trophy-outline' : 'skull-outline'} size={16} color={m.won ? '#22c55e' : '#f87171'} />
            <Text style={{ color: colors.text, flex: 1, fontWeight: '600' }} numberOfLines={1}>{m.room_id}</Text>
            <Text style={{ color: subText, fontSize: 12 }}>{m.kills}/{m.deaths}</Text>
            <Pressable
              onPress={() => shareMatch(m)}
              style={[styles.smallBtn, { borderColor: colors.primary, flexDirection: 'row', alignItems: 'center', gap: 5 }]}
              data-testid={`fps-game-share-match-${m.match_id}`} testID={`fps-game-share-match-${m.match_id}`}
            >
              <Ionicons name="share-social-outline" size={13} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }}>
                {sharedMatchId === m.match_id ? tx('fpsGame.recent.shareCopied', 'Link copied') : tx('fpsGame.recent.share', 'Share')}
              </Text>
            </Pressable>
          </View>
        ))}
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="fps-game-leaderboard-card" testID="fps-game-leaderboard-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('fpsGame.leaderboard.title', 'Kill leaderboard')}</Text>
        {leaderboard.length === 0 ? (
          <Text style={{ color: subText }}>{tx('fpsGame.leaderboard.empty', 'No matches recorded yet. Be the first on the board.')}</Text>
        ) : leaderboard.map((row) => (
          <View key={`${row.rank}-${row.display_name}`} style={[styles.roomRow, { borderColor: border }]}>
            <Text style={{ color: colors.primary, fontWeight: '800', width: 26 }}>#{row.rank}</Text>
            <Text style={{ color: colors.text, flex: 1, fontWeight: '600' }} numberOfLines={1}>{row.display_name}</Text>
            <Text style={{ color: subText, fontSize: 12 }}>
              {row.kills} {tx('fpsGame.leaderboard.kills', 'kills')} · K/D {row.kd_ratio}
            </Text>
          </View>
        ))}
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="fps-game-howto-card" testID="fps-game-howto-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('fpsGame.howto.title', 'How to play')}</Text>
        <Text style={{ color: subText, lineHeight: 20 }}>
          {tx('fpsGame.howto.desktop', 'Desktop: click the arena to lock your mouse. WASD to move, Shift to run, Space to jump, click to fire the AK-47.')}
        </Text>
        <Text style={{ color: subText, lineHeight: 20, marginTop: 6 }}>
          {tx('fpsGame.howto.mobile', 'Mobile: drag the left side to move, drag the right side to aim, and use the on-screen FIRE and JUMP buttons.')}
        </Text>
        <Text style={{ color: subText, lineHeight: 20, marginTop: 6 }}>
          {tx('fpsGame.howto.rules', 'Every hit deals 10 damage. Eliminate opponents to score kills — you respawn 3 seconds after going down.')}
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 14, backgroundColor: 'rgba(239,68,68,0.08)' },
  card: { borderWidth: 1, borderRadius: 16, padding: 18, marginBottom: 16 },
  cardTitle: { fontSize: 17, fontWeight: '800', marginBottom: 10 },
  label: { fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6, marginTop: 8 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 4 },
  modelRow: { flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginTop: 4 },
  modelCard: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1.5, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  inviteBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 16, paddingVertical: 12, marginTop: 16 },
  invitedBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, padding: 10, marginBottom: 12 },
  joinBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 999, paddingVertical: 13, marginTop: 16, minWidth: 220 },
  joinBtnText: { color: '#fff' /* @theme-ok deliberate-high-contrast */, fontWeight: '800', fontSize: 15 },
  roomRow: { flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 10 },
  smallBtn: { borderWidth: 1.5, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6 },
  shareJoinsChip: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', backgroundColor: 'rgba(34,197,94,0.10)', borderWidth: 1, borderColor: 'rgba(34,197,94,0.35)', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, marginTop: 10 },
});
