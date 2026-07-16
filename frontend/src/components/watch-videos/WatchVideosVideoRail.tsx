import React, { useEffect, useState } from 'react';
import { Image, ImageBackground, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type VideoItem = any;

const CATEGORY_ACCENT_PALETTE = [
  'rgba(255, 87, 87, 1)',
  'rgba(87, 180, 255, 1)',
  'rgba(255, 175, 74, 1)',
  'rgba(129, 227, 140, 1)',
  'rgba(193, 127, 255, 1)',
  'rgba(255, 120, 194, 1)',
  'rgba(92, 241, 220, 1)',
];

const categoryAccentColor = (category: string) => {
  const text = String(category || 'general').toLowerCase();
  let sum = 0;
  for (let i = 0; i < text.length; i += 1) sum += text.charCodeAt(i);
  return CATEGORY_ACCENT_PALETTE[sum % CATEGORY_ACCENT_PALETTE.length];
};

const formatDuration = (seconds: number): string => {
  const safe = Math.max(0, Number(seconds || 0));
  const hrs = Math.floor(safe / 3600);
  const mins = Math.floor((safe % 3600) / 60);
  if (hrs > 0) return `${hrs}h ${mins}m`;
  return `${Math.max(1, mins)}m`;
};

type RailProps = {
  title: string;
  testId: string;
  items: VideoItem[];
  activeVideoId?: string;
  colors: any;
  showReasons: boolean;
  currentPlan: string;
  lockReasonByVideo: Record<string, string>;
  onBlockedPress: (video: VideoItem, reason: string) => void;
  onUpgradePress: (video: VideoItem) => void;
  onPlay: (video: VideoItem, source: string) => void;
};

const PLAN_LEVELS: Record<string, number> = { free: 0, basic: 1, premium: 2 };
const normalizePlan = (value: string | undefined | null) => String(value || 'free').trim().toLowerCase();
const getPlanLockReasonForVideo = (video: VideoItem, currentPlan: string): string => {
  const requiredPlan = normalizePlan(video?.min_plan || 'free');
  const activePlan = normalizePlan(currentPlan);
  const requiredRank = PLAN_LEVELS[requiredPlan] ?? 0;
  const activeRank = PLAN_LEVELS[activePlan] ?? 0;
  if (requiredRank <= activeRank) return '';
  return `Locked: Requires ${requiredPlan.toUpperCase()} plan. Upgrade to watch this title.`;
};

const toBlurPlaceholderUri = (uri: string) => {
  if (!uri) return '';
  const joiner = uri.includes('?') ? '&' : '?';
  return `${uri}${joiner}blur=8`;
};

const ProgressiveImageBackground = ({ uri, style, imageStyle, placeholderTestId, children }: any) => {
  const [loaded, setLoaded] = useState(false);
  const src = String(uri || '').trim();
  const placeholderUri = toBlurPlaceholderUri(src);

  useEffect(() => {
    setLoaded(false);
  }, [src]);

  return (
    <View style={[style, { overflow: 'hidden', backgroundColor: 'rgba(18,22,30,0.72)' }]}>
      {placeholderUri ? (
        <Image accessibilityLabel="Decorative image"
          source={{ uri: placeholderUri }}
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, transform: [{ scale: 1.06 }], opacity: loaded ? 0 : 1 }}
          resizeMode="cover"
        />
      ) : null}

      <ImageBackground
        source={{ uri: src || undefined }}
        style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
        imageStyle={[imageStyle, { opacity: loaded ? 1 : 0.04 }]}
        onLoadEnd={() => setLoaded(true)}
      >
        {children}
      </ImageBackground>

      {!loaded ? (
        <View
          style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(16,20,28,0.22)' }}
          data-testid={placeholderTestId}
          testID={placeholderTestId}
          pointerEvents="none"
        />
      ) : null}
    </View>
  );
};

export default function VideoRail({
  title,
  testId,
  items,
  activeVideoId,
  colors,
  showReasons,
  currentPlan,
  lockReasonByVideo,
  onBlockedPress,
  onUpgradePress,
  onPlay,
}: RailProps) {
  if (!items.length) return null;

  return (
    <View
      style={{ marginHorizontal: 16, marginBottom: 18 }}
      data-testid={`${testId}-section`}
      testID={`${testId}-section`}
    >
      <View style={{ marginBottom: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text
          style={{ color: colors.text, fontSize: 16, fontWeight: '800' }}
          data-testid={`${testId}-title`}
          testID={`${testId}-title`}
        >
          {title}
        </Text>
        <View
          style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}44`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 9, paddingVertical: 4 }}
          data-testid={`${testId}-rail-pill`}
          testID={`${testId}-rail-pill`}
        >
          <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>CURATED</Text>
        </View>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 10, paddingRight: 4 }}
        data-testid={`${testId}-scroll`}
        testID={`${testId}-scroll`}
      >
        {items.map((video) => {
          const active = activeVideoId === video.video_id;
          const accent = categoryAccentColor(video.category);
          const lockReason = getPlanLockReasonForVideo(video, currentPlan);
          const isLocked = Boolean(lockReason);
          return (
            <TouchableOpacity
              key={video.video_id}
              onPress={() => {
                if (isLocked) {
                  onBlockedPress(video, lockReason);
                  return;
                }
                onPlay(video, `${testId}_rail`);
              }}
              style={{
                width: '100%',
                maxWidth: 960,
                borderRadius: 18,
                overflow: 'hidden',
                borderWidth: 1,
                borderColor: active ? `${accent.replace('1)', '0.75)')}` : colors.border,
                backgroundColor: colors.card,
                shadowColor: 'rgba(0,0,0,0.45)',
                shadowOpacity: active ? 0.35 : 0.22,
                shadowRadius: active ? 12 : 8,
                shadowOffset: { width: 0, height: 5 },
              }}
              data-testid={`${testId}-item-${video.video_id}`}
              testID={`${testId}-item-${video.video_id}`}
            >
              <ProgressiveImageBackground
                uri={video.thumbnail_url || ''}
                style={{ aspectRatio: 16 / 9, justifyContent: 'flex-end' }}
                imageStyle={{ opacity: active ? 0.95 : 0.9 }}
                placeholderTestId={`${testId}-thumb-placeholder-${video.video_id}`}
              >
                <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(7,10,18,0.22)' }} />
                <View style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '62%', backgroundColor: 'rgba(7,10,18,0.68)' }} />

                <View style={{ position: 'absolute', top: 8, left: 8, flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 999, backgroundColor: accent }} />
                  <View style={{ paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.5)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.2)' }}>
                    <Text numberOfLines={1} style={{ color: 'rgba(255,255,255,1)', fontSize: 10.5, fontWeight: '700' }}>
                      {video.category}
                    </Text>
                  </View>
                </View>

                <View style={{ position: 'absolute', top: 8, right: 8, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999, backgroundColor: 'rgba(0,0,0,0.48)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.16)' }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    {isLocked ? <Ionicons name="lock-closed-outline" size={10} color="rgba(255,255,255,0.92)" /> : null}
                    <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 10.5, fontWeight: '700' }}>{video.min_plan.toUpperCase()}</Text>
                  </View>
                </View>

                <View style={{ padding: 10 }}>
                  <Text numberOfLines={1} style={{ color: 'rgba(255,255,255,1)', fontSize: 12.5, fontWeight: '700' }}>
                    {video.quality_label || 'HD'} • {formatDuration(video.duration_seconds)}
                  </Text>
                </View>
              </ProgressiveImageBackground>

              <View style={{ padding: 10 }}>
                <Text numberOfLines={2} style={{ color: colors.text, fontSize: 13, fontWeight: '700' }}>
                  {video.title}
                </Text>
                <View
                  style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 8, paddingVertical: 4 }}
                  data-testid={`${testId}-content-type-badge-${video.video_id}`}
                  testID={`${testId}-content-type-badge-${video.video_id}`}
                >
                  <Text style={{ color: colors.primary, fontSize: 10, fontWeight: '800' }}>VIDEO</Text>
                </View>
                <Text numberOfLines={1} style={{ marginTop: 4, color: colors.textSec, fontSize: 11.5 }}>
                  {video.category} • {Number(video.view_count || 0)} views
                </Text>
                {lockReasonByVideo[video.video_id] ? (
                  <View
                    style={{ marginTop: 6, borderRadius: 8, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}14`, paddingHorizontal: 8, paddingVertical: 6 }}
                    data-testid={`${testId}-lock-tooltip-${video.video_id}`}
                    testID={`${testId}-lock-tooltip-${video.video_id}`}
                  >
                    <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }} numberOfLines={2}>
                      {lockReasonByVideo[video.video_id]}
                    </Text>
                    <TouchableOpacity
                      onPress={() => onUpgradePress(video)}
                      style={{ marginTop: 6, alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: `${colors.warningText}66`, backgroundColor: `${colors.warningText}22`, paddingHorizontal: 9, paddingVertical: 5, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                      data-testid={`${testId}-lock-upgrade-cta-${video.video_id}`}
                      testID={`${testId}-lock-upgrade-cta-${video.video_id}`}
                    >
                      <Ionicons name="arrow-up-circle-outline" size={11} color={colors.warningText} />
                      <Text style={{ color: colors.warningText, fontSize: 10.5, fontWeight: '700' }}>Upgrade to unlock</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
                {showReasons && (video.recommendation_reason || []).length > 0 ? (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 7 }}>
                    {(video.recommendation_reason || []).slice(0, 2).map((reason: string, idx: number) => (
                      <View
                        key={`${video.video_id}-reason-${idx}`}
                        style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}44`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 8, paddingVertical: 4 }}
                        data-testid={`${testId}-reason-${video.video_id}-${idx}`}
                        testID={`${testId}-reason-${video.video_id}-${idx}`}
                      >
                        <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '700' }} numberOfLines={1}>
                          {reason}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}
