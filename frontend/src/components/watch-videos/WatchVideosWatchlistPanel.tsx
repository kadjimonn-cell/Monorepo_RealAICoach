import React from 'react';
import VideoRail from './WatchVideosVideoRail';

type Props = {
  colors: any;
  selectedVideo: any;
  showRecommendationReasons: boolean;
  quotaPlan: string;
  lockReasonByVideo: Record<string, string>;
  showBlockedCardTooltip: (video: any, reason: string) => void;
  handleUpgradeFromLockedCard: (video: any) => void;
  playVideo: (video: any, source: string) => void;
  sortedWatchlistItems: any[];
  continueWatchingItems: any[];
  recommendedItems: any[];
  officialSpotlightItems: any[];
  trendingItems: any[];
  todayDropItems: any[];
  categoryRows: Record<string, any[]>;
};

export const WatchVideosWatchlistPanel = ({
  colors,
  selectedVideo,
  showRecommendationReasons,
  quotaPlan,
  lockReasonByVideo,
  showBlockedCardTooltip,
  handleUpgradeFromLockedCard,
  playVideo,
  sortedWatchlistItems,
  continueWatchingItems,
  recommendedItems,
  officialSpotlightItems,
  trendingItems,
  todayDropItems,
  categoryRows,
}: Props) => {
  return (
    <>
      <VideoRail
        title="My watchlist"
        testId="watch-videos-v2-watchlist"
        items={sortedWatchlistItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />
      <VideoRail
        title="Continue watching"
        testId="watch-videos-v2-continue"
        items={continueWatchingItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />
      <VideoRail
        title="Because you watched"
        testId="watch-videos-v2-recommended"
        items={recommendedItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />
      <VideoRail
        title="Official Videos Spotlight"
        testId="watch-videos-v2-official-spotlight"
        items={officialSpotlightItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />
      <VideoRail
        title="Trending now"
        testId="watch-videos-v2-trending"
        items={trendingItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />
      <VideoRail
        title="Today’s drops"
        testId="watch-videos-v2-daily"
        items={todayDropItems}
        activeVideoId={selectedVideo?.video_id}
        colors={colors}
        showReasons={showRecommendationReasons}
        currentPlan={quotaPlan}
        lockReasonByVideo={lockReasonByVideo}
        onBlockedPress={showBlockedCardTooltip}
        onUpgradePress={handleUpgradeFromLockedCard}
        onPlay={playVideo}
      />

      {Object.entries(categoryRows || {}).slice(0, 6).map(([category, rows]) => (
        <VideoRail
          key={category}
          title={category}
          testId={`watch-videos-v2-category-rail-${category.toLowerCase().replace(/\s+/g, '-')}`}
          items={rows}
          activeVideoId={selectedVideo?.video_id}
          colors={colors}
          showReasons={showRecommendationReasons}
          currentPlan={quotaPlan}
          lockReasonByVideo={lockReasonByVideo}
          onBlockedPress={showBlockedCardTooltip}
          onUpgradePress={handleUpgradeFromLockedCard}
          onPlay={playVideo}
        />
      ))}
    </>
  );
};
