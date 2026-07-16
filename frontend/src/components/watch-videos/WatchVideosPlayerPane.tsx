import React from 'react';
import {
  ActivityIndicator,
  Linking,
  Platform,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  colors: any;
  baseCardStyle: any;
  selectedVideo: any;
  selectedPlayback: any;
  youtubeLoadedVideoId: string;
  setYoutubeLoadedVideoId: (value: string) => void;
  setForceFallbackPlaybackByVideo: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  setPlayIntentNonce: React.Dispatch<React.SetStateAction<number>>;
  playIntentNonce: number;
  videoRef: React.MutableRefObject<any>;
  setCurrentPlaybackSeconds: (value: number) => void;
  syncProgress: (forceComplete?: boolean) => Promise<void>;
  playNextInQueue: () => Promise<void>;
  setUnavailableVideoIds: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  openExternal: () => Promise<void>;
  savingProgress: boolean;
  feedbackByVideo: Record<string, string>;
  handleFeedback: (videoId: string, feedback: 'like' | 'dislike' | 'clear', showUndo?: boolean, previousOverride?: string) => Promise<void>;
  autoplayNextEnabled: boolean;
  toggleAutoplayNext: () => void;
  watchlistByVideo: Record<string, boolean>;
  toggleWatchlist: (videoId: string) => Promise<void>;
  nextUpVideo: any;
  nextUpEtaSeconds: number;
  skipToNextNow: () => Promise<void>;
  formatDuration: (seconds: number) => string;
  compactNumber: (value: number) => string;
  setPlayerCardOffsetY: (value: number) => void;
};

const WebIframe = (props: Record<string, any>) => React.createElement('iframe', props);

export const WatchVideosPlayerPane = ({
  colors,
  baseCardStyle,
  selectedVideo,
  selectedPlayback,
  youtubeLoadedVideoId,
  setYoutubeLoadedVideoId,
  setForceFallbackPlaybackByVideo,
  setPlayIntentNonce,
  playIntentNonce,
  videoRef,
  setCurrentPlaybackSeconds,
  syncProgress,
  playNextInQueue,
  setUnavailableVideoIds,
  openExternal,
  savingProgress,
  feedbackByVideo,
  handleFeedback,
  autoplayNextEnabled,
  toggleAutoplayNext,
  watchlistByVideo,
  toggleWatchlist,
  nextUpVideo,
  nextUpEtaSeconds,
  skipToNextNow,
  formatDuration,
  compactNumber,
  setPlayerCardOffsetY,
}: Props) => {
  return (
    <View
      style={{ marginHorizontal: 16, marginBottom: 16, ...baseCardStyle, borderRadius: 22, padding: 12 }}
      onLayout={(event) => setPlayerCardOffsetY(event?.nativeEvent?.layout?.y || 0)}
      data-testid="watch-videos-v2-player-card"
      testID="watch-videos-v2-player-card"
    >
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text style={{ color: colors.text, fontSize: 15.5, fontWeight: '800', flex: 1 }} data-testid="watch-videos-v2-player-title" testID="watch-videos-v2-player-title">
          {selectedVideo?.title || 'Select any video from rails or grid'}
        </Text>
        {savingProgress ? <ActivityIndicator size="small" color={colors.primary} data-testid="watch-videos-v2-player-syncing" /> : null}
      </View>

      <View style={{ marginTop: 10, borderRadius: 16, overflow: 'hidden', borderWidth: 1, borderColor: `${colors.primary}44`, backgroundColor: colors.bgSoft }}>
        {selectedPlayback.can_play ? (
          Platform.OS === 'web' ? (
            selectedPlayback.primary_kind === 'youtube' ? (
              <View style={{ width: '100%', aspectRatio: '16 / 9' } as any} data-testid="watch-videos-v2-youtube-player-wrap" testID="watch-videos-v2-youtube-player-wrap">
                <WebIframe
                  key={`${selectedVideo?.video_id || 'none'}-youtube`}
                  src={selectedPlayback.primary_url}
                  style={{ border: 'none', width: '100%', height: '100%' }}
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                  allowFullScreen
                  onLoad={() => {
                    if (selectedVideo?.video_id) {
                      setYoutubeLoadedVideoId(selectedVideo.video_id);
                    }
                  }}
                  data-testid="watch-videos-v2-youtube-player"
                />
                {selectedPlayback.fallback_url ? (
                  <TouchableOpacity
                    onPress={() => {
                      if (!selectedVideo?.video_id) return;
                      setForceFallbackPlaybackByVideo((prev) => ({ ...prev, [selectedVideo.video_id]: true }));
                      setPlayIntentNonce((prev) => prev + 1);
                    }}
                    style={{
                      position: 'absolute',
                      right: 10,
                      bottom: 10,
                      borderRadius: 999,
                      borderWidth: 1,
                      borderColor: `${colors.primary}66`,
                      backgroundColor: `${colors.primary}12`,
                      paddingHorizontal: 10,
                      paddingVertical: 6,
                    }}
                    data-testid="watch-videos-v2-player-fallback-button"
                    testID="watch-videos-v2-player-fallback-button"
                  >
                    <Text style={{ color: colors.primary, fontSize: 11.5, fontWeight: '700' }}>Use backup stream</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ) : (
              <video
                key={`${selectedVideo?.video_id || 'none'}-mp4-${playIntentNonce}`}
                ref={(node) => { videoRef.current = node; }}
                controls
                autoPlay
                playsInline
                preload="metadata"
                poster={selectedVideo?.thumbnail_url || undefined}
                src={selectedPlayback.primary_url}
                onLoadedMetadata={() => {
                  if (videoRef.current && (selectedVideo?.progress_seconds || 0) > 0) {
                    videoRef.current.currentTime = Number(selectedVideo?.progress_seconds || 0);
                  }
                  setCurrentPlaybackSeconds(Math.max(0, Number(selectedVideo?.progress_seconds || 0)));
                }}
                onTimeUpdate={() => {
                  if (videoRef.current) {
                    setCurrentPlaybackSeconds(Math.max(0, Math.floor(videoRef.current.currentTime || 0)));
                  }
                  void syncProgress(false);
                }}
                onEnded={() => {
                  void syncProgress(true);
                  void playNextInQueue();
                }}
                onError={() => {
                  if (selectedVideo?.video_id) {
                    setUnavailableVideoIds((prev) => ({ ...prev, [selectedVideo.video_id]: true }));
                  }
                  void playNextInQueue();
                }}
                style={{ width: '100%', aspectRatio: '16 / 9' } as any}
                data-testid="watch-videos-v2-html-player"
              />
            )
          ) : (
            <View style={{ padding: 20, alignItems: 'center' }} data-testid="watch-videos-v2-player-native" testID="watch-videos-v2-player-native">
              <Ionicons name="videocam-outline" size={24} color={colors.textMuted} />
              <TouchableOpacity onPress={openExternal} style={{ marginTop: 10 }} data-testid="watch-videos-v2-player-open-external" testID="watch-videos-v2-player-open-external">
                <Text style={{ color: colors.primary, fontWeight: '700' }}>Open stream</Text>
              </TouchableOpacity>
            </View>
          )
        ) : (
          <View style={{ padding: 32, alignItems: 'center' }} data-testid="watch-videos-v2-player-empty" testID="watch-videos-v2-player-empty">
            <Text style={{ color: colors.textSec }}>No video selected</Text>
          </View>
        )}
      </View>

      {selectedVideo ? (
        <>
          <View
            style={{
              marginTop: 10,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: `${colors.primary}40`,
              backgroundColor: `${colors.primary}0E`,
              paddingHorizontal: 10,
              paddingVertical: 8,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 8,
            }}
            data-testid="watch-videos-v2-player-momentum-ribbon"
            testID="watch-videos-v2-player-momentum-ribbon"
          >
            <Ionicons name="sparkles-outline" size={14} color={colors.primary} />
            <Text style={{ color: colors.text, fontSize: 11.5, fontWeight: '700', flex: 1 }}>
              Momentum Mode: recommendations adapt instantly to your like/dislike signals.
            </Text>
          </View>

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="watch-videos-v2-player-meta" testID="watch-videos-v2-player-meta">
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 11, paddingVertical: 7 }}>
              <Text style={{ color: colors.textSec, fontSize: 11.5 }}>{selectedVideo.category}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 11, paddingVertical: 7 }}>
              <Text style={{ color: colors.textSec, fontSize: 11.5 }}>{formatDuration(selectedVideo.duration_seconds)}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 11, paddingVertical: 7 }}>
              <Text style={{ color: colors.textSec, fontSize: 11.5 }}>{`${compactNumber(selectedVideo.view_count)} views`}</Text>
            </View>
            <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 11, paddingVertical: 7 }} data-testid="watch-videos-v2-player-source-label" testID="watch-videos-v2-player-source-label">
              <Text style={{ color: colors.primary, fontSize: 11.5 }}>{selectedPlayback.source_label}</Text>
            </View>
            <View
              style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.successText}66`, backgroundColor: `${colors.successText}14`, paddingHorizontal: 11, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="watch-videos-v2-player-source-trust-badge"
              testID="watch-videos-v2-player-source-trust-badge"
            >
              <Ionicons name="shield-checkmark-outline" size={12} color={colors.successText} />
              <Text style={{ color: colors.successText, fontSize: 11.5, fontWeight: '700' }}>
                {`${selectedPlayback.source_trust_badge} • ${selectedPlayback.source_channel}`}
              </Text>
            </View>

            <TouchableOpacity
              onPress={() => handleFeedback(selectedVideo.video_id, 'like', true)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: feedbackByVideo[selectedVideo.video_id] === 'like' ? `${colors.successText}77` : colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 11, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="watch-videos-v2-feedback-like"
              testID="watch-videos-v2-feedback-like"
            >
              <Ionicons name="thumbs-up-outline" size={13} color={feedbackByVideo[selectedVideo.video_id] === 'like' ? colors.successText : colors.textMuted} />
              <Text style={{ color: feedbackByVideo[selectedVideo.video_id] === 'like' ? colors.successText : colors.textSec, fontSize: 11.5 }}>Like</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => handleFeedback(selectedVideo.video_id, 'dislike', true)}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: feedbackByVideo[selectedVideo.video_id] === 'dislike' ? `${colors.error}77` : colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 11, paddingVertical: 7, flexDirection: 'row', alignItems: 'center', gap: 6 }}
              data-testid="watch-videos-v2-feedback-dislike"
              testID="watch-videos-v2-feedback-dislike"
            >
              <Ionicons name="thumbs-down-outline" size={13} color={feedbackByVideo[selectedVideo.video_id] === 'dislike' ? colors.error : colors.textMuted} />
              <Text style={{ color: feedbackByVideo[selectedVideo.video_id] === 'dislike' ? colors.error : colors.textSec, fontSize: 11.5 }}>Dislike</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={toggleAutoplayNext}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: autoplayNextEnabled ? `${colors.successText}66` : colors.border,
                backgroundColor: autoplayNextEnabled ? `${colors.successText}15` : colors.bgSoft,
                paddingHorizontal: 11,
                paddingVertical: 7,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
              }}
              data-testid="watch-videos-v2-autoplay-next-toggle"
              testID="watch-videos-v2-autoplay-next-toggle"
            >
              <Ionicons name={autoplayNextEnabled ? 'play-forward' : 'play-forward-outline'} size={13} color={autoplayNextEnabled ? colors.successText : colors.textMuted} />
              <Text style={{ color: autoplayNextEnabled ? colors.successText : colors.textSec, fontSize: 11.5 }}>
                {autoplayNextEnabled ? 'Autoplay Next On' : 'Autoplay Next Off'}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => toggleWatchlist(selectedVideo.video_id)}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: watchlistByVideo[selectedVideo.video_id] ? `${colors.primary}77` : colors.border,
                backgroundColor: watchlistByVideo[selectedVideo.video_id] ? `${colors.primary}12` : colors.bgSoft,
                paddingHorizontal: 11,
                paddingVertical: 7,
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
              }}
              data-testid="watch-videos-v2-watchlist-toggle"
              testID="watch-videos-v2-watchlist-toggle"
            >
              <Ionicons name={watchlistByVideo[selectedVideo.video_id] ? 'bookmark' : 'bookmark-outline'} size={13} color={watchlistByVideo[selectedVideo.video_id] ? colors.primary : colors.textMuted} />
              <Text style={{ color: watchlistByVideo[selectedVideo.video_id] ? colors.primary : colors.textSec, fontSize: 11.5 }}>
                {watchlistByVideo[selectedVideo.video_id] ? 'Saved' : 'Watchlist'}
              </Text>
            </TouchableOpacity>
          </View>

          <View
            style={{
              marginTop: 10,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: nextUpVideo ? `${colors.primary}55` : colors.border,
              backgroundColor: nextUpVideo ? `${colors.primary}10` : colors.bgSoft,
              paddingHorizontal: 12,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 10,
            }}
            data-testid="watch-videos-v2-next-up-tile"
            testID="watch-videos-v2-next-up-tile"
          >
            <Ionicons name="play-skip-forward-outline" size={15} color={nextUpVideo ? colors.primary : colors.textMuted} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '700' }} data-testid="watch-videos-v2-next-up-title" testID="watch-videos-v2-next-up-title">
                {nextUpVideo ? `Next up: ${nextUpVideo.title}` : 'Next up queue is unavailable'}
              </Text>
              <Text style={{ color: colors.textSec, fontSize: 11, marginTop: 2 }} data-testid="watch-videos-v2-next-up-eta" testID="watch-videos-v2-next-up-eta">
                {nextUpVideo ? `ETA ${formatDuration(nextUpEtaSeconds)} • ${nextUpVideo.category}` : 'No eligible video found to queue next'}
              </Text>
            </View>
            <TouchableOpacity
              onPress={skipToNextNow}
              disabled={!nextUpVideo}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: nextUpVideo ? `${colors.primary}66` : colors.border,
                backgroundColor: nextUpVideo ? `${colors.primary}16` : colors.bgSoft,
                paddingHorizontal: 10,
                paddingVertical: 7,
                opacity: nextUpVideo ? 1 : 0.6,
              }}
              data-testid="watch-videos-v2-next-up-skip-button"
              testID="watch-videos-v2-next-up-skip-button"
            >
              <Text style={{ color: nextUpVideo ? colors.primary : colors.textMuted, fontSize: 11.5, fontWeight: '700' }}>
                Skip now
              </Text>
            </TouchableOpacity>
          </View>
        </>
      ) : null}
    </View>
  );
};
