import React from 'react';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  colors: any;
  baseCardStyle: any;
  displayGridItems: any[];
  selectedVideo: any;
  gridCardWidth: any;
  gridColumns: number;
  activeFeed: string;
  showRecommendationReasons: boolean;
  lockReasonByVideo: Record<string, string>;
  watchlistByVideo: Record<string, boolean>;
  categoryAccentColor: (category: string) => string;
  getPlanLockReasonForVideo: (video: any, currentPlan: string) => string;
  quotaPlan: string;
  toggleWatchlist: (videoId: string) => Promise<void>;
  playVideo: (video: any, source: string) => Promise<void>;
  showBlockedCardTooltip: (video: any, reason: string) => void;
  handleUpgradeFromLockedCard: (video: any) => void;
  compactNumber: (value: number) => string;
  ProgressiveImageBackground: any;
};

export const WatchVideosCatalogGrid = ({
  colors,
  baseCardStyle,
  displayGridItems,
  selectedVideo,
  gridCardWidth,
  gridColumns,
  activeFeed,
  showRecommendationReasons,
  lockReasonByVideo,
  watchlistByVideo,
  categoryAccentColor,
  getPlanLockReasonForVideo,
  quotaPlan,
  toggleWatchlist,
  playVideo,
  showBlockedCardTooltip,
  handleUpgradeFromLockedCard,
  compactNumber,
  ProgressiveImageBackground,
}: Props) => {
  const sectionTitle = activeFeed === 'trending'
    ? 'Trending catalog'
    : activeFeed === 'new'
      ? 'New release catalog'
      : 'Explore all videos';

  return (
    <>
      <View
        style={{
          marginHorizontal: 16,
          marginBottom: 10,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: `${colors.primary}35`,
          backgroundColor: `${colors.primary}0D`,
          paddingHorizontal: 12,
          paddingVertical: 10,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
        data-testid="watch-videos-v2-grid-header"
        testID="watch-videos-v2-grid-header"
      >
        <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}>{sectionTitle}</Text>
        <View
          style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}14`, paddingHorizontal: 9, paddingVertical: 4 }}
          data-testid="watch-videos-v2-grid-content-pill"
          testID="watch-videos-v2-grid-content-pill"
        >
          <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '800' }}>VIDEO FEED</Text>
        </View>
      </View>

      <View
        style={{
          marginHorizontal: 16,
          flexDirection: 'row',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          rowGap: 11,
          columnGap: 8,
        }}
        data-testid="watch-videos-v2-grid"
        testID="watch-videos-v2-grid"
      >
        {displayGridItems.map((video) => {
          const active = selectedVideo?.video_id === video.video_id;
          const accent = categoryAccentColor(video.category);
          const lockReason = getPlanLockReasonForVideo(video, quotaPlan);
          const isLocked = Boolean(lockReason);
          return (
            <TouchableOpacity
              key={video.video_id}
              onPress={() => {
                if (isLocked) {
                  showBlockedCardTooltip(video, lockReason);
                  return;
                }
                void playVideo(video, 'grid_select');
              }}
              style={{
                width: gridCardWidth as any,
                minWidth: gridColumns === 1 ? '100%' as any : 220,
                ...baseCardStyle,
                borderColor: active ? accent.replace('1)', '0.75)') : colors.border,
                borderWidth: 1,
                borderRadius: 18,
                shadowColor: 'rgba(0,0,0,0.38)',
                shadowOpacity: active ? 0.35 : 0.18,
                shadowOffset: { width: 0, height: 6 },
                shadowRadius: active ? 12 : 8,
              }}
              data-testid={`watch-videos-v2-grid-item-${video.video_id}`}
              testID={`watch-videos-v2-grid-item-${video.video_id}`}
            >
              <ProgressiveImageBackground
                uri={video.thumbnail_url || ''}
                style={{ aspectRatio: 16 / 9, justifyContent: 'space-between' }}
                imageStyle={{ opacity: active ? 0.95 : 0.9 }}
                placeholderTestId={`watch-videos-v2-grid-thumb-placeholder-${video.video_id}`}
              >
                <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(8,12,18,0.2)' }} />
                <View style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '64%', backgroundColor: 'rgba(8,12,18,0.7)' }} />

                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', margin: 8 }}>
                  <View style={{ alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.55)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.16)' }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                      {isLocked ? <Ionicons name="lock-closed-outline" size={10} color="rgba(255,255,255,0.92)" /> : null}
                      <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 10.5, fontWeight: '700' }}>{video.min_plan.toUpperCase()}</Text>
                    </View>
                  </View>
                  <View style={{ alignItems: 'center', flexDirection: 'row', gap: 6 }}>
                    <View style={{ width: 7, height: 7, borderRadius: 999, backgroundColor: accent }} />
                    <Text style={{ color: 'rgba(255,255,255,0.95)', fontSize: 10.5, fontWeight: '700' }}>{video.category}</Text>
                  </View>
                </View>
                <View style={{ padding: 8, backgroundColor: 'rgba(0,0,0,0.42)' }}>
                  <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 11.5, fontWeight: '700' }}>{video.quality_label} • {video.duration_seconds ? `${Math.max(1, Math.floor(video.duration_seconds / 60))}m` : '—'}</Text>
                </View>
              </ProgressiveImageBackground>

              <View style={{ padding: 10 }}>
                <View
                  style={{ alignSelf: 'flex-start', marginBottom: 5, borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 8, paddingVertical: 4 }}
                  data-testid={`watch-videos-v2-grid-content-type-badge-${video.video_id}`}
                  testID={`watch-videos-v2-grid-content-type-badge-${video.video_id}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>VIDEO</Text>
                </View>
                <Text numberOfLines={2} style={{ color: colors.text, fontSize: 12.8, fontWeight: '700' }}>{video.title}</Text>
                {lockReasonByVideo[video.video_id] ? (
                  <View
                    style={{ marginTop: 6, borderRadius: 8, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}14`, paddingHorizontal: 8, paddingVertical: 6 }}
                    data-testid={`watch-videos-v2-grid-lock-tooltip-${video.video_id}`}
                    testID={`watch-videos-v2-grid-lock-tooltip-${video.video_id}`}
                  >
                    <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }} numberOfLines={2}>
                      {lockReasonByVideo[video.video_id]}
                    </Text>
                    <TouchableOpacity
                      onPress={() => handleUpgradeFromLockedCard(video)}
                      style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}22`, paddingHorizontal: 9, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                      data-testid={`watch-videos-v2-grid-lock-upgrade-cta-${video.video_id}`}
                      testID={`watch-videos-v2-grid-lock-upgrade-cta-${video.video_id}`}
                    >
                      <Ionicons name="arrow-up-circle-outline" size={11} color={colors.warningText} />
                      <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }}>Upgrade to unlock</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>
                  {video.category} • {video.studio}
                </Text>
                {showRecommendationReasons && (video.recommendation_reason || []).length > 0 ? (
                  <Text
                    numberOfLines={1}
                    style={{ marginTop: 4, color: colors.primary, fontSize: 10.5, fontWeight: '700' }}
                    data-testid={`watch-videos-v2-grid-reason-${video.video_id}`}
                    testID={`watch-videos-v2-grid-reason-${video.video_id}`}
                  >
                    {video.recommendation_reason?.[0]}
                  </Text>
                ) : null}
                <View style={{ marginTop: 7, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10.8 }}>{compactNumber(video.view_count)} views</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                    <TouchableOpacity
                      onPress={() => void toggleWatchlist(video.video_id)}
                      data-testid={`watch-videos-v2-grid-watchlist-toggle-${video.video_id}`}
                      testID={`watch-videos-v2-grid-watchlist-toggle-${video.video_id}`}
                    >
                      <Ionicons
                        name={watchlistByVideo[video.video_id] ? 'bookmark' : 'bookmark-outline'}
                        size={15}
                        color={watchlistByVideo[video.video_id] ? colors.primary : colors.textMuted}
                      />
                    </TouchableOpacity>
                    <Ionicons name="play-circle-outline" size={16} color={colors.primary} />
                  </View>
                </View>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      {displayGridItems.length === 0 ? (
        <View style={{ marginHorizontal: 16, marginTop: 20, alignItems: 'center' }} data-testid="watch-videos-v2-grid-empty" testID="watch-videos-v2-grid-empty">
          <Ionicons name="search-outline" size={24} color={colors.textMuted} />
          <Text style={{ marginTop: 8, color: colors.textSec }}>No videos found for this filter</Text>
        </View>
      ) : null}
    </>
  );
};
