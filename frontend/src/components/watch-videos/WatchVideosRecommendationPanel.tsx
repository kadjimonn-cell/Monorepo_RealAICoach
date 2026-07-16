import React from 'react';
import { Image, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  colors: any;
  watchlistSortMode: 'recent' | 'duration' | 'category';
  watchlistSortDirection: 'asc' | 'desc';
  setWatchlistSortMode: (value: 'recent' | 'duration' | 'category') => void;
  setWatchlistSortDirection: React.Dispatch<React.SetStateAction<'asc' | 'desc'>>;
  applyVisualPreferencePatch: (patch: any) => void;
  sagaContinuityGroups: any[];
  recommendedItems: any[];
  quotaPlan: string;
  lockReasonByVideo: Record<string, string>;
  showBlockedCardTooltip: (video: any, reason: string) => void;
  playVideo: (video: any, source: string) => void;
  getPlanLockReasonForVideo: (video: any, currentPlan: string) => string;
};

export const WatchVideosRecommendationPanel = ({
  colors,
  watchlistSortMode,
  watchlistSortDirection,
  setWatchlistSortMode,
  setWatchlistSortDirection,
  applyVisualPreferencePatch,
  sagaContinuityGroups,
  recommendedItems,
  quotaPlan,
  showBlockedCardTooltip,
  playVideo,
  getPlanLockReasonForVideo,
}: Props) => {
  const recommendationQualityAvg = Number(
    ((recommendedItems || []).slice(0, 12).reduce((acc: number, row: any) => acc + Number(row?.recommendation_score || 0), 0)
      / Math.max(1, Math.min(12, (recommendedItems || []).length || 0))),
  ) || 0;

  const topSignals = Object.entries(
    ((recommendedItems || []).slice(0, 16).reduce((bag: Record<string, number>, row: any) => {
      const signals = Array.isArray(row?.recommendation_signals) ? row.recommendation_signals : [];
      signals.forEach((signal: string) => {
        const clean = String(signal || '').trim();
        if (!clean) return;
        bag[clean] = (bag[clean] || 0) + 1;
      });
      return bag;
    }, {} as Record<string, number>)) || {},
  )
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .slice(0, 4);

  return (
    <>
      <View
        style={{
          marginHorizontal: 16,
          marginTop: 8,
          marginBottom: 8,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: `${colors.successText}44`,
          backgroundColor: `${colors.successText}10`,
          paddingHorizontal: 12,
          paddingVertical: 10,
        }}
        data-testid="watch-videos-v2-recommendation-quality-wrap"
        testID="watch-videos-v2-recommendation-quality-wrap"
      >
        <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '800' }} data-testid="watch-videos-v2-recommendation-quality-title" testID="watch-videos-v2-recommendation-quality-title">
          Recommendation quality tuning
        </Text>
        <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 11.2 }} data-testid="watch-videos-v2-recommendation-quality-subtitle" testID="watch-videos-v2-recommendation-quality-subtitle">
          Adaptive scoring blends freshness, history affinity, completion intent, and queue behavior.
        </Text>
        <View style={{ marginTop: 8, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}14`, paddingHorizontal: 10, paddingVertical: 6 }} data-testid="watch-videos-v2-recommendation-quality-avg-score" testID="watch-videos-v2-recommendation-quality-avg-score">
            <Text style={{ color: colors.successText, fontSize: 11, fontWeight: '800' }}>{`Avg score: ${recommendationQualityAvg.toFixed(1)}`}</Text>
          </View>
          {topSignals.map(([signal, count], idx) => (
            <View
              key={`rec-signal-${signal}-${idx}`}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 9, paddingVertical: 5 }}
              data-testid={`watch-videos-v2-recommendation-quality-signal-${idx}`}
              testID={`watch-videos-v2-recommendation-quality-signal-${idx}`}
            >
              <Text style={{ color: colors.primary, fontSize: 10.8, fontWeight: '700' }}>{`${signal.replace(/_/g, ' ')} • ${count}`}</Text>
            </View>
          ))}
        </View>
      </View>

      <View
        style={{
          marginHorizontal: 16,
          marginTop: 14,
          marginBottom: 6,
          borderRadius: 14,
          borderWidth: 1,
          borderColor: `${colors.primary}38`,
          backgroundColor: `${colors.primary}0D`,
          paddingHorizontal: 10,
          paddingVertical: 9,
          flexDirection: 'row',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 8,
        }}
        data-testid="watch-videos-v2-watchlist-sort-wrap"
        testID="watch-videos-v2-watchlist-sort-wrap"
      >
        <Text style={{ color: colors.textMuted, fontSize: 11.5 }} data-testid="watch-videos-v2-watchlist-sort-label" testID="watch-videos-v2-watchlist-sort-label">
          Sort watchlist:
        </Text>
        {([
          { key: 'recent', label: 'Recently added' },
          { key: 'duration', label: 'Duration' },
          { key: 'category', label: 'Category' },
        ] as { key: 'recent' | 'duration' | 'category'; label: string }[]).map((item) => {
          const active = watchlistSortMode === item.key;
          return (
            <TouchableOpacity
              key={item.key}
              onPress={() => {
                setWatchlistSortMode(item.key);
                applyVisualPreferencePatch({ watchlist_sort_mode: item.key });
              }}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: active ? `${colors.primary}77` : colors.border,
                backgroundColor: active ? `${colors.primary}16` : colors.card,
                paddingHorizontal: 10,
                paddingVertical: 6,
              }}
              data-testid={`watch-videos-v2-watchlist-sort-${item.key}`}
              testID={`watch-videos-v2-watchlist-sort-${item.key}`}
            >
              <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11.5, fontWeight: active ? '700' : '500' }}>
                {item.label}
              </Text>
            </TouchableOpacity>
          );
        })}

        <TouchableOpacity
          onPress={() => {
            setWatchlistSortDirection((prev) => {
              const next = prev === 'desc' ? 'asc' : 'desc';
              applyVisualPreferencePatch({ watchlist_sort_direction: next });
              return next;
            });
          }}
          style={{
            borderRadius: 999,
            borderWidth: 1,
            borderColor: `${colors.primary}66`,
            backgroundColor: `${colors.primary}12`,
            paddingHorizontal: 10,
            paddingVertical: 6,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 6,
          }}
          data-testid="watch-videos-v2-watchlist-sort-direction-toggle"
          testID="watch-videos-v2-watchlist-sort-direction-toggle"
        >
          <Ionicons
            name={watchlistSortDirection === 'asc' ? 'arrow-up-outline' : 'arrow-down-outline'}
            size={12}
            color={colors.primary}
          />
          <Text style={{ color: colors.primary, fontSize: 11.5, fontWeight: '700' }}>
            {watchlistSortDirection === 'asc' ? 'Ascending' : 'Descending'}
          </Text>
        </TouchableOpacity>
      </View>

      {sagaContinuityGroups.map((group) => (
        <View key={`saga-${group.key}`} style={{ marginBottom: 12 }} data-testid={`watch-videos-v2-saga-group-${group.key}`} testID={`watch-videos-v2-saga-group-${group.key}`}>
          <Text style={{ color: colors.text, fontSize: 15, fontWeight: '900', marginBottom: 4 }}>{`Movie Saga Continuity • ${group.name}`}</Text>
          <View style={{ alignSelf: 'flex-start', borderRadius: 10, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 10, paddingVertical: 6, marginBottom: 8 }}>
            <Text style={{ color: colors.textSec, fontSize: 11.5 }}>{group.recap}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
            {group.items.map((video: any, idx: number) => {
              const lockReason = getPlanLockReasonForVideo(video, quotaPlan);
              const isLocked = Boolean(lockReason);
              return (
                <TouchableOpacity
                  key={`saga-item-${group.key}-${video.video_id}-${idx}`}
                  onPress={() => {
                    if (isLocked) {
                      showBlockedCardTooltip(video, lockReason);
                      return;
                    }
                    playVideo(video, `saga:${group.key}`);
                  }}
                  style={{ width: '100%', maxWidth: 960, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, overflow: 'hidden' }}
                  data-testid={`watch-videos-v2-saga-item-${video.video_id}`}
                  testID={`watch-videos-v2-saga-item-${video.video_id}`}
                >
                  <View style={{ width: '100%', aspectRatio: '16 / 9', backgroundColor: colors.bgSoft }}>
                    {video.thumbnail_url ? <Image source={{ uri: video.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel={video.title} /> : null}
                  </View>
                  <View style={{ padding: 10 }}>
                    <View style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 8, paddingVertical: 4 }}>
                      <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>{`PART ${video.saga_order || idx + 1}`}</Text>
                    </View>
                    <Text style={{ color: colors.text, fontSize: 12.5, fontWeight: '700', marginTop: 6 }} numberOfLines={2}>{video.title}</Text>
                    <Text style={{ color: colors.textSec, fontSize: 10.8, marginTop: 4 }} numberOfLines={1}>{video.category} • {video.studio}</Text>
                  </View>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
      ))}
    </>
  );
};
