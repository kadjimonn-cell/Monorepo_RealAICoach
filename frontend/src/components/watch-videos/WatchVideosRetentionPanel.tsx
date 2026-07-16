import React, { useMemo } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type VideoItem = {
  video_id: string;
  title: string;
  category?: string;
  duration_seconds?: number;
  progress_seconds?: number;
  recommendation_reason?: string[];
};

type Props = {
  colors: any;
  baseCardStyle: any;
  continueQueueItems: VideoItem[];
  watchlistItems: VideoItem[];
  recommendedItems: VideoItem[];
  sagaResumeItem: any;
  retentionProfile: any;
  selectedVideo: VideoItem | null;
  feedbackByVideo: Record<string, string>;
  playVideo: (video: VideoItem, source: string) => Promise<void>;
};

const formatDuration = (seconds: number) => {
  const safe = Math.max(0, Number(seconds || 0));
  const mins = Math.max(1, Math.floor(safe / 60));
  return `${mins}m`;
};

export const WatchVideosRetentionPanel = ({
  colors,
  baseCardStyle,
  continueQueueItems,
  watchlistItems,
  recommendedItems,
  sagaResumeItem,
  retentionProfile,
  selectedVideo,
  feedbackByVideo,
  playVideo,
}: Props) => {
  const missionFocusLabels: Record<string, string> = {
    continue_queue: 'Protect your continue queue momentum',
    watchlist_to_play: 'Convert watchlist into active plays',
    finish_in_progress: 'Close in-progress titles for stronger retention',
    feedback_tune: 'Refine recommendation quality with quick feedback',
    daily_return: 'Rebuild daily return habit',
    kickoff_watchlist: 'Kick off your watchlist momentum',
  };

  const missionTarget = useMemo(() => {
    const sagaVideo = sagaResumeItem?.resume_video;
    if (sagaVideo?.video_id) {
      return {
        kind: 'resume_saga',
        label: `Resume ${String(sagaResumeItem?.saga_name || 'Saga')}`,
        reason: String(sagaResumeItem?.resume_reason || 'Continue your narrative momentum.'),
        video: sagaVideo,
      };
    }
    if (continueQueueItems[0]?.video_id) {
      return {
        kind: 'continue_queue',
        label: 'Continue queue mission',
        reason: 'Finish your in-progress title before switching contexts.',
        video: continueQueueItems[0],
      };
    }
    if (watchlistItems[0]?.video_id) {
      return {
        kind: 'watchlist_kickoff',
        label: 'Watchlist kickoff mission',
        reason: 'Start your saved title now to keep your binge cadence alive.',
        video: watchlistItems[0],
      };
    }
    return null;
  }, [continueQueueItems, sagaResumeItem, watchlistItems]);

  const queueCandidates = useMemo(() => {
    const rows = continueQueueItems.filter((item) => item?.video_id);
    return rows.slice(0, 4);
  }, [continueQueueItems]);

  const recommendationReasons = useMemo(() => {
    const bag = new Set<string>();
    for (const item of recommendedItems || []) {
      const reasons = Array.isArray(item?.recommendation_reason) ? item.recommendation_reason : [];
      for (const reason of reasons) {
        const clean = String(reason || '').trim();
        if (clean) bag.add(clean);
        if (bag.size >= 6) break;
      }
      if (bag.size >= 6) break;
    }
    return Array.from(bag);
  }, [recommendedItems]);

  const sessionStreak = useMemo(() => {
    if (retentionProfile && typeof retentionProfile === 'object') {
      const score = Math.max(0, Math.min(100, Number(retentionProfile?.score || 0)));
      const level = String(retentionProfile?.level || 'Warm-up');
      const adaptiveSignals = retentionProfile?.adaptive_signals || {};
      return {
        score,
        level,
        normalized: score,
        likedCount: Math.round(Number(adaptiveSignals?.likes_ratio_pct || 0) / 10),
        startedCount: Number(adaptiveSignals?.continue_queue_depth || continueQueueItems.length || 0),
      };
    }

    const likedCount = Object.values(feedbackByVideo || {}).filter((value) => String(value) === 'like').length;
    const startedCount = continueQueueItems.filter((item) => Number(item?.progress_seconds || 0) > 0).length;
    const completedCandidate = selectedVideo && Number(selectedVideo?.progress_seconds || 0) > 0 ? 1 : 0;
    const score = Math.max(0, likedCount * 2 + startedCount + completedCandidate);
    const level = score >= 8 ? 'Unstoppable' : score >= 4 ? 'Hot streak' : 'Warm-up';
    const normalized = Math.min(100, Math.round((score / 10) * 100));
    return { score, level, normalized, likedCount, startedCount };
  }, [continueQueueItems, feedbackByVideo, retentionProfile, selectedVideo]);

  const missionFocus = String(retentionProfile?.mission_focus || '').trim();
  const streakRewards = retentionProfile?.streak_rewards && typeof retentionProfile.streak_rewards === 'object'
    ? retentionProfile.streak_rewards
    : null;
  const streakBadges = Array.isArray(streakRewards?.badges_unlocked)
    ? streakRewards.badges_unlocked.slice(-4)
    : [];
  const nextMilestone = streakRewards?.next_milestone && typeof streakRewards.next_milestone === 'object'
    ? streakRewards.next_milestone
    : null;
  const streakStatus = String(streakRewards?.streak_status || '').toLowerCase();
  const streakStatusColor = streakStatus === 'active'
    ? colors.successText
    : (streakStatus === 'at_risk' ? colors.warningText : colors.textSec);
  const streakStatusLabel = streakStatus === 'active'
    ? 'Active streak'
    : (streakStatus === 'at_risk' ? 'At risk today' : 'Cold streak');
  const churnRisk = String(retentionProfile?.churn_risk || 'medium').toLowerCase();
  const churnRiskColor = churnRisk === 'high' ? colors.error : (churnRisk === 'low' ? colors.successText : colors.warningText);
  const churnRiskLabel = churnRisk === 'high' ? 'High churn risk' : churnRisk === 'low' ? 'Low churn risk' : 'Medium churn risk';
  const nextBestActions = Array.isArray(retentionProfile?.next_best_actions)
    ? retentionProfile.next_best_actions.slice(0, 2)
    : [];

  return (
    <View
      style={{ marginHorizontal: 16, marginBottom: 14, borderRadius: 20, padding: 12, ...baseCardStyle }}
      data-testid="watch-videos-v2-retention-panel"
      testID="watch-videos-v2-retention-panel"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900' }} data-testid="watch-videos-v2-retention-title" testID="watch-videos-v2-retention-title">
          Binge Momentum
        </Text>
        <View
          style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 9, paddingVertical: 4 }}
          data-testid="watch-videos-v2-retention-phase-pill"
          testID="watch-videos-v2-retention-phase-pill"
        >
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>PHASE 3</Text>
        </View>
      </View>

      {missionTarget ? (
        <View
          style={{ marginTop: 10, borderRadius: 14, borderWidth: 1, borderColor: `${colors.primary}52`, backgroundColor: `${colors.primary}10`, padding: 10 }}
          data-testid="watch-videos-v2-mission-strip"
          testID="watch-videos-v2-mission-strip"
        >
          <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }} data-testid="watch-videos-v2-mission-label" testID="watch-videos-v2-mission-label">
            {missionTarget.label}
          </Text>
          <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }} data-testid="watch-videos-v2-mission-reason" testID="watch-videos-v2-mission-reason">
            {missionTarget.reason}
          </Text>
          <TouchableOpacity
            onPress={() => { void playVideo(missionTarget.video, `phase3_mission_${missionTarget.kind}`); }}
            style={{ marginTop: 8, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}88`, backgroundColor: `${colors.primary}20`, paddingHorizontal: 12, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
            data-testid="watch-videos-v2-mission-play-button"
            testID="watch-videos-v2-mission-play-button"
          >
            <Ionicons name="play" size={12} color={colors.primary} />
            <Text style={{ color: colors.primary, fontSize: 11.5, fontWeight: '800' }}>Play mission now</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View style={{ marginTop: 10 }} data-testid="watch-videos-v2-session-streak-wrap" testID="watch-videos-v2-session-streak-wrap">
        <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }} data-testid="watch-videos-v2-session-streak-title" testID="watch-videos-v2-session-streak-title">
          Session streak: {sessionStreak.level}
        </Text>
        <Text style={{ marginTop: 3, color: colors.textSec, fontSize: 11 }} data-testid="watch-videos-v2-session-streak-metrics" testID="watch-videos-v2-session-streak-metrics">
          {`${sessionStreak.score} points • ${sessionStreak.startedCount} in progress • ${sessionStreak.likedCount} likes`}
        </Text>
        <View style={{ marginTop: 6, height: 8, borderRadius: 999, backgroundColor: `${colors.primary}22`, overflow: 'hidden' }}>
          <View
            style={{ height: '100%', width: `${sessionStreak.normalized}%`, backgroundColor: colors.primary }}
            data-testid="watch-videos-v2-session-streak-progress"
            testID="watch-videos-v2-session-streak-progress"
          />
        </View>
      </View>

      {streakRewards ? (
        <View
          style={{ marginTop: 11, borderRadius: 13, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}10`, padding: 10 }}
          data-testid="watch-videos-v2-streak-rewards-wrap"
          testID="watch-videos-v2-streak-rewards-wrap"
        >
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid="watch-videos-v2-streak-rewards-current-badge" testID="watch-videos-v2-streak-rewards-current-badge">
              <Text style={{ color: colors.primary, fontSize: 10.8, fontWeight: '800' }}>{`Badge: ${String(streakRewards?.current_badge || 'Not unlocked')}`}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${streakStatusColor}66`, backgroundColor: `${streakStatusColor}15`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid="watch-videos-v2-streak-rewards-status" testID="watch-videos-v2-streak-rewards-status">
              <Text style={{ color: streakStatusColor, fontSize: 10.8, fontWeight: '800' }}>{`${streakStatusLabel} • ${Number(streakRewards?.current_streak_days || 0)} days`}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.borderStrong, backgroundColor: `${colors.textSec}14`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid="watch-videos-v2-streak-rewards-points" testID="watch-videos-v2-streak-rewards-points">
              <Text style={{ color: colors.text, fontSize: 10.8, fontWeight: '800' }}>{`${Number(streakRewards?.points || 0)} pts`}</Text>
            </View>
          </View>

          {streakBadges.length > 0 ? (
            <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', gap: 7 }} data-testid="watch-videos-v2-streak-rewards-badge-list" testID="watch-videos-v2-streak-rewards-badge-list">
              {streakBadges.map((badge: any, idx: number) => (
                <View
                  key={`streak-badge-${idx}`}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: colors.card, paddingHorizontal: 9, paddingVertical: 5 }}
                  data-testid={`watch-videos-v2-streak-reward-badge-${idx}`}
                  testID={`watch-videos-v2-streak-reward-badge-${idx}`}
                >
                  <Text style={{ color: colors.text, fontSize: 10.5, fontWeight: '700' }}>
                    {`${String(badge?.badge_title || 'Badge')} • ${Number(badge?.required_days || 0)}d`}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}

          {nextMilestone ? (
            <View style={{ marginTop: 9 }} data-testid="watch-videos-v2-streak-rewards-next-milestone" testID="watch-videos-v2-streak-rewards-next-milestone">
              <Text style={{ color: colors.text, fontSize: 11.2, fontWeight: '700' }} data-testid="watch-videos-v2-streak-rewards-next-label" testID="watch-videos-v2-streak-rewards-next-label">
                {`Next milestone: ${String(nextMilestone?.badge_title || 'Badge')} (${Number(nextMilestone?.required_days || 0)} days)`}
              </Text>
              <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 10.8 }} data-testid="watch-videos-v2-streak-rewards-next-reward" testID="watch-videos-v2-streak-rewards-next-reward">
                {`${String(nextMilestone?.reward_label || 'Reward active')} • ${Number(nextMilestone?.remaining_days || 0)} day(s) left`}
              </Text>
              <View style={{ marginTop: 6, height: 7, borderRadius: 999, backgroundColor: `${colors.primary}20`, overflow: 'hidden' }}>
                <View
                  style={{ height: '100%', width: `${Math.max(0, Math.min(100, Number(nextMilestone?.progress_pct || 0)))}%`, backgroundColor: colors.primary }}
                  data-testid="watch-videos-v2-streak-rewards-next-progress"
                  testID="watch-videos-v2-streak-rewards-next-progress"
                />
              </View>
            </View>
          ) : null}
        </View>
      ) : null}

      {retentionProfile ? (
        <View
          style={{ marginTop: 11, borderRadius: 13, borderWidth: 1, borderColor: `${churnRiskColor}66`, backgroundColor: `${churnRiskColor}14`, padding: 10 }}
          data-testid="watch-videos-v2-retention-adaptive-wrap"
          testID="watch-videos-v2-retention-adaptive-wrap"
        >
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid="watch-videos-v2-retention-adaptive-score" testID="watch-videos-v2-retention-adaptive-score">
              <Text style={{ color: colors.primary, fontSize: 10.8, fontWeight: '800' }}>{`Adaptive score: ${Number(retentionProfile?.score || 0)}`}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${churnRiskColor}66`, backgroundColor: `${churnRiskColor}12`, paddingHorizontal: 9, paddingVertical: 5 }} data-testid="watch-videos-v2-retention-adaptive-risk" testID="watch-videos-v2-retention-adaptive-risk">
              <Text style={{ color: churnRiskColor, fontSize: 10.8, fontWeight: '800' }}>{`${churnRiskLabel} • ${Number(retentionProfile?.risk_pct || 0)}%`}</Text>
            </View>
          </View>

          {missionFocus ? (
            <Text style={{ marginTop: 7, color: colors.text, fontSize: 11.3, fontWeight: '700' }} data-testid="watch-videos-v2-retention-adaptive-mission-focus" testID="watch-videos-v2-retention-adaptive-mission-focus">
              {missionFocusLabels[missionFocus] || 'Adaptive mission guidance active'}
            </Text>
          ) : null}

          {nextBestActions.map((action: string, idx: number) => (
            <Text
              key={`retention-action-${idx}`}
              style={{ marginTop: 5, color: colors.textSec, fontSize: 10.8 }}
              data-testid={`watch-videos-v2-retention-adaptive-action-${idx}`}
              testID={`watch-videos-v2-retention-adaptive-action-${idx}`}
            >
              {`• ${action}`}
            </Text>
          ))}
        </View>
      ) : null}

      {queueCandidates.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="watch-videos-v2-smart-next-wrap" testID="watch-videos-v2-smart-next-wrap">
          <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginBottom: 8 }} data-testid="watch-videos-v2-smart-next-title" testID="watch-videos-v2-smart-next-title">
            Smart Next Queue
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {queueCandidates.map((item, idx) => {
              const urgency = idx === 0 ? 'NOW' : idx === 1 ? 'NEXT' : 'QUEUE';
              const urgencyColor = idx === 0 ? colors.error : idx === 1 ? colors.warningText : colors.primary;
              return (
                <TouchableOpacity
                  key={`smart-next-${item.video_id}`}
                  onPress={() => { void playVideo(item, `phase3_smart_next_${idx}`); }}
                  style={{ width: '100%', maxWidth: 960, borderRadius: 14, borderWidth: 1, borderColor: `${urgencyColor}77`, backgroundColor: colors.card, padding: 9 }}
                  data-testid={`watch-videos-v2-smart-next-item-${item.video_id}`}
                  testID={`watch-videos-v2-smart-next-item-${item.video_id}`}
                >
                  <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${urgencyColor}77`, backgroundColor: `${urgencyColor}18`, paddingHorizontal: 8, paddingVertical: 4 }}>
                    <Text style={{ color: urgencyColor, fontSize: 10, fontWeight: '900' }}>{urgency}</Text>
                  </View>
                  <Text style={{ marginTop: 7, color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={2}>
                    {item.title}
                  </Text>
                  <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 10.8 }} numberOfLines={1}>
                    {`${item.category || 'Video'} • ${formatDuration(Number(item.duration_seconds || 0))}`}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ) : null}

      {recommendationReasons.length > 0 ? (
        <View style={{ marginTop: 12 }} data-testid="watch-videos-v2-reason-chip-cluster" testID="watch-videos-v2-reason-chip-cluster">
          <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800', marginBottom: 7 }} data-testid="watch-videos-v2-reason-chip-title" testID="watch-videos-v2-reason-chip-title">
            Why this feed is picking these titles
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
            {recommendationReasons.map((reason, idx) => (
              <View
                key={`reason-chip-${idx}`}
                style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}4D`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 9, paddingVertical: 5 }}
                data-testid={`watch-videos-v2-reason-chip-${idx}`}
                testID={`watch-videos-v2-reason-chip-${idx}`}
              >
                <Text style={{ color: colors.primary, fontSize: 10.8, fontWeight: '700' }}>{reason}</Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}
    </View>
  );
};
