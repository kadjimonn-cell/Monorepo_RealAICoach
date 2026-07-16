import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useTheme } from '../../context/ThemeContext';
import { useLanguage } from '../../i18n/LanguageContext';
import FlappyBirdGame, { FlappyDifficulty, medalForScore } from './FlappyBirdGame';

type LeaderRow = { rank: number; user_id?: string; display_name: string; best_score: number; games_played: number; medal?: string };
type RankInfo = { rank: number; best_score: number; total_players: number };
type DailyChallenge = { target: number; completed_today: boolean; streak: number };
type XpInfo = { earned_today: number; daily_cap: number; per_run_cap: number };

const MEDAL_COLORS: Record<string, string> = { bronze: '#cd7f32', silver: '#94a3b8', gold: '#f59e0b', diamond: '#38bdf8' };
const DIFFICULTIES: FlappyDifficulty[] = ['easy', 'classic', 'hard'];

export default function FlappyBirdHub() {
  const { colors, darkMode } = useTheme();
  const { t } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [personalBest, setPersonalBest] = useState(0);
  const [gamesPlayed, setGamesPlayed] = useState(0);
  const [bestByDifficulty, setBestByDifficulty] = useState<Record<string, number>>({});
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([]);
  const [weeklyLeaderboard, setWeeklyLeaderboard] = useState<LeaderRow[]>([]);
  const [myRank, setMyRank] = useState<RankInfo | null>(null);
  const [myWeeklyRank, setMyWeeklyRank] = useState<RankInfo | null>(null);
  const [daily, setDaily] = useState<DailyChallenge | null>(null);
  const [xpInfo, setXpInfo] = useState<XpInfo | null>(null);
  const [newBest, setNewBest] = useState(false);
  const [lastXpAwarded, setLastXpAwarded] = useState(0);
  const [challengeJustDone, setChallengeJustDone] = useState(false);
  const [difficulty, setDifficulty] = useState<FlappyDifficulty>('classic');
  const [boardTab, setBoardTab] = useState<'weekly' | 'all_time'>('weekly');
  const [shareCopied, setShareCopied] = useState(false);

  const applyPayload = useCallback((data: any) => {
    setPersonalBest(Number(data?.personal_best || 0));
    setGamesPlayed(Number(data?.games_played || 0));
    setBestByDifficulty(data?.best_by_difficulty || {});
    setLeaderboard(data?.leaderboard || []);
    setWeeklyLeaderboard(data?.weekly_leaderboard || []);
    setMyRank(data?.my_rank || null);
    setMyWeeklyRank(data?.my_weekly_rank || null);
    setDaily(data?.daily_challenge || null);
    setXpInfo(data?.xp || null);
  }, []);

  const loadBootstrap = useCallback(async () => {
    try {
      setError('');
      const resp = await api.get('/flappy-bird/bootstrap');
      applyPayload(resp.data);
    } catch (err: any) {
      setError(String(err?.response?.data?.detail || err?.message || tx('flappyBird.errors.loadFailed', 'Unable to load the Flappy Bird game.')));
    } finally {
      setLoading(false);
    }
  }, [applyPayload, tx]);

  useEffect(() => { loadBootstrap(); }, [loadBootstrap]);

  const handleGameOver = useCallback(async (score: number, durationMs: number) => {
    try {
      const resp = await api.post('/flappy-bird/score', { score, duration_ms: durationMs, difficulty });
      applyPayload(resp.data);
      setLastXpAwarded(Number(resp.data?.xp_awarded || 0));
      setChallengeJustDone(Boolean(resp.data?.daily_challenge_completed_now));
      setNewBest(Boolean(resp.data?.is_new_best) && score > 0);
      if (resp.data?.is_new_best && score > 0) {
        setTimeout(() => setNewBest(false), 5000);
      }
      if (resp.data?.daily_challenge_completed_now) {
        setTimeout(() => setChallengeJustDone(false), 6000);
      }
    } catch { /* score submission is best-effort; gameplay continues offline */ }
  }, [applyPayload, difficulty]);

  const handleShare = useCallback(async () => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const origin = window.location.origin.replace(/\/+$/, '');
    const template = tx('flappyBird.share.text', 'I scored {score} points in Flappy Bird on RealAICoach — can you beat me? {link}');
    const message = template
      .replace('{score}', String(personalBest))
      .replace('{link}', `${origin}/features/flappy-bird`);
    try {
      await navigator.clipboard.writeText(message);
    } catch {
      try {
        const ta = document.createElement('textarea');
        ta.value = message;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      } catch { /* clipboard unavailable */ }
    }
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 3000);
  }, [personalBest, tx]);

  if (loading) {
    return (
      <View style={[styles.center, { paddingVertical: 60 }]} data-testid="flappy-bird-loading-state" testID="flappy-bird-loading-state">
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  const cardBg = darkMode ? 'rgba(255,255,255,0.04)' : colors.card;
  const border = darkMode ? 'rgba(255,255,255,0.09)' : 'rgba(15,23,42,0.10)';
  const subText = colors.textSec;
  const activeRows = boardTab === 'weekly' ? weeklyLeaderboard : leaderboard;
  const activeRank = boardTab === 'weekly' ? myWeeklyRank : myRank;
  const inTopList = Boolean(activeRank && activeRank.rank > 0 && activeRank.rank <= activeRows.length);

  const diffLabel = (d: FlappyDifficulty) =>
    d === 'easy' ? tx('flappyBird.difficulty.easy', 'Easy')
      : d === 'hard' ? tx('flappyBird.difficulty.hard', 'Hard')
      : tx('flappyBird.difficulty.classic', 'Classic');

  return (
    <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingBottom: 48 }} data-testid="flappy-bird-hub" testID="flappy-bird-hub">
      {!!error && (
        <View style={[styles.errorBanner, { borderColor: colors.error }]} data-testid="flappy-bird-error" testID="flappy-bird-error">
          <Ionicons name="warning-outline" size={16} color={colors.error} />
          <Text style={{ color: colors.error, flex: 1 }}>{error}</Text>
        </View>
      )}

      <View style={styles.statsRow}>
        <View style={[styles.statCard, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-best-score-card" testID="flappy-bird-best-score-card">
          <Ionicons name="trophy-outline" size={18} color={colors.warning} />
          <Text style={[styles.statValue, { color: colors.text }]}>{personalBest}</Text>
          <Text style={[styles.statLabel, { color: subText }]}>{tx('flappyBird.stats.personalBest', 'Personal best')}</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-games-played-card" testID="flappy-bird-games-played-card">
          <Ionicons name="game-controller-outline" size={18} color={colors.primary} />
          <Text style={[styles.statValue, { color: colors.text }]}>{gamesPlayed}</Text>
          <Text style={[styles.statLabel, { color: subText }]}>{tx('flappyBird.stats.gamesPlayed', 'Games played')}</Text>
        </View>
        <View style={[styles.statCard, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-xp-card" testID="flappy-bird-xp-card">
          <Ionicons name="flash-outline" size={18} color={colors.success} />
          <Text style={[styles.statValue, { color: colors.text }]}>{xpInfo?.earned_today ?? 0}</Text>
          <Text style={[styles.statLabel, { color: subText }]}>{tx('flappyBird.stats.xpToday', 'XP today')} / {xpInfo?.daily_cap ?? 100}</Text>
        </View>
      </View>

      {daily && (
        <View style={[styles.dailyCard, { backgroundColor: cardBg, borderColor: daily.completed_today ? colors.success : border }]} data-testid="flappy-bird-daily-challenge-card" testID="flappy-bird-daily-challenge-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Ionicons name={daily.completed_today ? 'checkmark-circle' : 'flag-outline'} size={20} color={daily.completed_today ? colors.success : colors.primary} />
            <Text style={{ color: colors.text, fontWeight: '800', fontSize: 15, flex: 1 }}>{tx('flappyBird.daily.title', 'Daily Challenge')}</Text>
            <View style={[styles.streakPill, { backgroundColor: colors.warningSoft, borderColor: colors.warning }]} data-testid="flappy-bird-daily-streak" testID="flappy-bird-daily-streak">
              <Ionicons name="flame" size={13} color={colors.warning} />
              <Text style={{ color: colors.warningText, fontWeight: '800', fontSize: 12 }}>{daily.streak} {tx('flappyBird.daily.streakLabel', 'day streak')}</Text>
            </View>
          </View>
          <Text style={{ color: subText, marginTop: 6 }}>
            {daily.completed_today
              ? tx('flappyBird.daily.done', 'Completed today — come back tomorrow to keep your streak alive!')
              : `${tx('flappyBird.daily.target', 'Score {target}+ in a single run today').replace('{target}', String(daily.target))} · ${tx('flappyBird.daily.bonus', '+20 XP bonus')}`}
          </Text>
          {challengeJustDone && (
            <Text style={{ color: colors.success, fontWeight: '800', marginTop: 6 }} data-testid="flappy-bird-daily-just-done" testID="flappy-bird-daily-just-done">
              {tx('flappyBird.daily.justDone', 'Daily challenge complete! +20 XP bonus earned.')}
            </Text>
          )}
        </View>
      )}

      {newBest && (
        <View style={[styles.newBestBanner, { borderColor: colors.success, backgroundColor: colors.successSoft }]} data-testid="flappy-bird-new-best-banner" testID="flappy-bird-new-best-banner">
          <Ionicons name="sparkles" size={16} color={colors.success} />
          <Text style={{ color: colors.success, fontWeight: '800', fontSize: 13, flex: 1 }}>
            {tx('flappyBird.stats.newBest', 'New personal best! Your record has been saved to the leaderboard.')}
          </Text>
          {lastXpAwarded > 0 && (
            <Text style={{ color: colors.successText, fontWeight: '900', fontSize: 13 }} data-testid="flappy-bird-xp-awarded" testID="flappy-bird-xp-awarded">+{lastXpAwarded} XP</Text>
          )}
        </View>
      )}

      <View style={styles.difficultyRow} data-testid="flappy-bird-difficulty-selector" testID="flappy-bird-difficulty-selector">
        <Text style={{ color: subText, fontWeight: '700', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, marginRight: 4 }}>
          {tx('flappyBird.difficulty.label', 'Difficulty')}
        </Text>
        {DIFFICULTIES.map((d) => {
          const active = difficulty === d;
          return (
            <TouchableOpacity
              key={d}
              onPress={() => setDifficulty(d)}
              style={[styles.diffPill, { backgroundColor: active ? colors.primary : cardBg, borderColor: active ? colors.primary : border }]}
              data-testid={`flappy-bird-difficulty-${d}`} testID={`flappy-bird-difficulty-${d}`}
            >
              <Text style={{ color: active ? colors.primaryText : colors.text, fontWeight: '800', fontSize: 12 }}>{diffLabel(d)}</Text>
              <Text style={{ color: active ? colors.primaryText : subText, fontSize: 10, fontWeight: '700' }}>
                {tx('flappyBird.difficulty.best', 'Best')}: {bestByDifficulty[d] ?? 0}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-game-card" testID="flappy-bird-game-card">
        <FlappyBirdGame onGameOver={handleGameOver} difficulty={difficulty} personalBest={personalBest} />
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-leaderboard-card" testID="flappy-bird-leaderboard-card">
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12, gap: 8 }}>
          <Text style={[styles.cardTitle, { color: colors.text, marginBottom: 0, flex: 1 }]}>{tx('flappyBird.leaderboard.title', 'High score leaderboard')}</Text>
          <TouchableOpacity
            onPress={() => setBoardTab('weekly')}
            style={[styles.tabPill, { backgroundColor: boardTab === 'weekly' ? colors.primary : cardBg, borderColor: boardTab === 'weekly' ? colors.primary : border }]}
            data-testid="flappy-bird-leaderboard-tab-weekly" testID="flappy-bird-leaderboard-tab-weekly"
          >
            <Text style={{ color: boardTab === 'weekly' ? colors.primaryText : colors.text, fontWeight: '800', fontSize: 12 }}>{tx('flappyBird.leaderboard.weekly', 'This week')}</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setBoardTab('all_time')}
            style={[styles.tabPill, { backgroundColor: boardTab === 'all_time' ? colors.primary : cardBg, borderColor: boardTab === 'all_time' ? colors.primary : border }]}
            data-testid="flappy-bird-leaderboard-tab-alltime" testID="flappy-bird-leaderboard-tab-alltime"
          >
            <Text style={{ color: boardTab === 'all_time' ? colors.primaryText : colors.text, fontWeight: '800', fontSize: 12 }}>{tx('flappyBird.leaderboard.allTime', 'All-time')}</Text>
          </TouchableOpacity>
        </View>

        {activeRows.length === 0 ? (
          <Text style={{ color: subText }}>{tx('flappyBird.leaderboard.empty', 'No scores recorded yet — be the first on the board!')}</Text>
        ) : activeRows.map((row) => (
          <View key={`${boardTab}-${row.rank}-${row.display_name}`} style={[styles.leaderRow, { borderColor: border }]}>
            <Text style={{ color: colors.primary, fontWeight: '800', width: 30 }}>#{row.rank}</Text>
            <Text style={{ color: colors.text, flex: 1, fontWeight: '600' }} numberOfLines={1}>{row.display_name}</Text>
            {row.medal && row.medal !== 'none' && (
              <Ionicons name="medal" size={15} color={MEDAL_COLORS[row.medal] || colors.warning} />
            )}
            <Text style={{ color: subText, fontSize: 12 }}>
              {row.best_score} {tx('flappyBird.leaderboard.points', 'pts')} · {row.games_played} {tx('flappyBird.leaderboard.games', 'games')}
            </Text>
          </View>
        ))}

        {activeRank && activeRank.rank > 0 && !inTopList && (
          <View style={[styles.leaderRow, styles.myRankRow, { borderColor: colors.primary, backgroundColor: colors.primarySoft }]} data-testid="flappy-bird-my-rank-row" testID="flappy-bird-my-rank-row">
            <Text style={{ color: colors.primary, fontWeight: '800', width: 30 }}>#{activeRank.rank}</Text>
            <Text style={{ color: colors.text, flex: 1, fontWeight: '800' }}>{tx('flappyBird.leaderboard.you', 'You')}</Text>
            {medalForScore(activeRank.best_score) !== 'none' && (
              <Ionicons name="medal" size={15} color={MEDAL_COLORS[medalForScore(activeRank.best_score)] || colors.warning} />
            )}
            <Text style={{ color: subText, fontSize: 12 }}>
              {activeRank.best_score} {tx('flappyBird.leaderboard.points', 'pts')} · {tx('flappyBird.leaderboard.of', 'of')} {activeRank.total_players}
            </Text>
          </View>
        )}

        <TouchableOpacity
          onPress={handleShare}
          style={[styles.shareBtn, { borderColor: colors.primary, backgroundColor: shareCopied ? colors.successSoft : colors.primarySoft }]}
          data-testid="flappy-bird-share-button" testID="flappy-bird-share-button"
        >
          <Ionicons name={shareCopied ? 'checkmark-circle-outline' : 'share-social-outline'} size={16} color={shareCopied ? colors.success : colors.primary} />
          <Text style={{ color: shareCopied ? colors.success : colors.primary, fontWeight: '800', fontSize: 13 }}>
            {shareCopied ? tx('flappyBird.share.copied', 'Challenge link copied to clipboard!') : tx('flappyBird.share.button', 'Challenge a friend')}
          </Text>
        </TouchableOpacity>
      </View>

      <View style={[styles.card, { backgroundColor: cardBg, borderColor: border }]} data-testid="flappy-bird-howto-card" testID="flappy-bird-howto-card">
        <Text style={[styles.cardTitle, { color: colors.text }]}>{tx('flappyBird.howto.title', 'How to play')}</Text>
        <Text style={{ color: subText, lineHeight: 20 }}>
          {tx('flappyBird.howto.controls', 'Desktop: press Space or click to flap. Mobile: tap the game area. Press P to pause, M or the speaker button to mute.')}
        </Text>
        <Text style={{ color: subText, lineHeight: 20, marginTop: 6 }}>
          {tx('flappyBird.howto.goal', 'Fly between the pipes without touching them, the ground, or the sky. Each pipe you pass earns one point — beat your personal best to climb the leaderboard!')}
        </Text>
        <Text style={{ color: subText, lineHeight: 20, marginTop: 6 }}>
          {tx('flappyBird.howto.upgrades', 'The game speeds up every 10 points. Earn medals at 10, 25, 50 and 100 points, collect XP for every run, and complete the daily challenge to build your streak.')}
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  errorBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 14, backgroundColor: 'rgba(239,68,68,0.08)' },
  statsRow: { flexDirection: 'row', gap: 12, marginBottom: 16 },
  statCard: { flex: 1, borderWidth: 1, borderRadius: 16, padding: 16, alignItems: 'center', gap: 4 },
  statValue: { fontSize: 26, fontWeight: '900' },
  statLabel: { fontSize: 11, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, textAlign: 'center' },
  dailyCard: { borderWidth: 1, borderRadius: 16, padding: 16, marginBottom: 16 },
  streakPill: { flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4 },
  newBestBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 16 },
  difficultyRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' },
  diffPill: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 8, alignItems: 'center', gap: 1 },
  card: { borderWidth: 1, borderRadius: 16, padding: 18, marginBottom: 16 },
  cardTitle: { fontSize: 17, fontWeight: '800', marginBottom: 10 },
  tabPill: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  leaderRow: { flexDirection: 'row', alignItems: 'center', gap: 10, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 10 },
  myRankRow: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, marginTop: 8, borderBottomWidth: 1 },
  shareBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1, borderRadius: 999, paddingVertical: 10, marginTop: 14 },
});
