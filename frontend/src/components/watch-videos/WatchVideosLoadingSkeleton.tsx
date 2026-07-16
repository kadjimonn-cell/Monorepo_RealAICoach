import React, { useEffect, useRef, useState } from 'react';
import { Animated, ScrollView, Text, View } from 'react-native';

type Props = {
  colors: any;
  baseCardStyle: any;
  width: number;
};

const SkeletonBlock = ({ width = '100%', height = 12, radius = 8, testId, delay = 0 }: { width?: any; height?: number; radius?: number; testId: string; delay?: number }) => {
  const opacity = useRef(new Animated.Value(0.35)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.75, duration: 720, delay, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.35, duration: 720, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [delay, opacity]);

  return (
    <Animated.View
      style={{ width, height, borderRadius: radius, opacity, backgroundColor: 'rgba(140,155,180,0.22)' }}
      data-testid={testId}
      testID={testId}
    />
  );
};

export const WatchVideosLoadingSkeleton = ({ colors, baseCardStyle, width }: Props) => {
  const [stage, setStage] = useState(1);

  useEffect(() => {
    const t1 = setTimeout(() => setStage(2), 180);
    const t2 = setTimeout(() => setStage(3), 360);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  const railCardWidth = width >= 900 ? 256 : width >= 700 ? 228 : 198;

  return (
    <View style={{ paddingVertical: 14, paddingBottom: 28 }} data-testid="watch-videos-v2-skeleton-root" testID="watch-videos-v2-skeleton-root">
      <View style={{ marginHorizontal: 16, marginBottom: 14 }} data-testid="watch-videos-v2-skeleton-status" testID="watch-videos-v2-skeleton-status">
        <Text style={{ color: colors.textSec, fontSize: 12.5, fontWeight: '600' }} data-testid="watch-videos-v2-skeleton-status-text" testID="watch-videos-v2-skeleton-status-text">
          Building your personalized video feed...
        </Text>
      </View>

      <View style={{ marginHorizontal: 16, marginBottom: 16, borderRadius: 22, overflow: 'hidden', ...baseCardStyle }} data-testid="watch-videos-v2-skeleton-hero" testID="watch-videos-v2-skeleton-hero">
        <SkeletonBlock height={width >= 900 ? 280 : 220} radius={22} testId="watch-videos-v2-skeleton-hero-media" />
        <View style={{ position: 'absolute', left: 18, right: 18, bottom: 16, gap: 8 }}>
          <SkeletonBlock width={110} height={18} radius={999} testId="watch-videos-v2-skeleton-hero-kicker" delay={100} />
          <SkeletonBlock width="78%" height={26} radius={9} testId="watch-videos-v2-skeleton-hero-title" delay={140} />
          <SkeletonBlock width="92%" height={12} testId="watch-videos-v2-skeleton-hero-line-1" delay={180} />
          <SkeletonBlock width="72%" height={12} testId="watch-videos-v2-skeleton-hero-line-2" delay={220} />
          <View style={{ marginTop: 4, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            <SkeletonBlock width={98} height={32} radius={999} testId="watch-videos-v2-skeleton-hero-btn-1" delay={250} />
            <SkeletonBlock width={132} height={32} radius={999} testId="watch-videos-v2-skeleton-hero-btn-2" delay={280} />
            <SkeletonBlock width={146} height={32} radius={999} testId="watch-videos-v2-skeleton-hero-btn-3" delay={320} />
          </View>
        </View>
      </View>

      {stage >= 1 ? (
        <View style={{ marginHorizontal: 16, marginBottom: 16, borderRadius: 22, padding: 12, ...baseCardStyle }} data-testid="watch-videos-v2-skeleton-player" testID="watch-videos-v2-skeleton-player">
          <SkeletonBlock width="66%" height={18} radius={9} testId="watch-videos-v2-skeleton-player-title" />
          <SkeletonBlock width="100%" height={width >= 900 ? 320 : 220} radius={14} testId="watch-videos-v2-skeleton-player-media" delay={120} />
          <View style={{ marginTop: 10, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            {[0, 1, 2, 3].map((chip) => (
              <SkeletonBlock key={`player-chip-${chip}`} width={96} height={28} radius={999} testId={`watch-videos-v2-skeleton-player-chip-${chip}`} delay={chip * 40} />
            ))}
          </View>
        </View>
      ) : null}

      {stage >= 2 ? (
        <>
          <View style={{ marginHorizontal: 16, marginBottom: 16, borderRadius: 18, padding: 12, ...baseCardStyle }} data-testid="watch-videos-v2-skeleton-recommendation" testID="watch-videos-v2-skeleton-recommendation">
            <SkeletonBlock width="48%" height={16} radius={8} testId="watch-videos-v2-skeleton-recommendation-title" />
            <SkeletonBlock width="90%" height={12} testId="watch-videos-v2-skeleton-recommendation-line-1" delay={120} />
            <SkeletonBlock width="84%" height={12} testId="watch-videos-v2-skeleton-recommendation-line-2" delay={180} />
            <View style={{ marginTop: 10, flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              {[0, 1, 2, 3].map((pill) => (
                <SkeletonBlock key={`rec-pill-${pill}`} width={pill % 2 === 0 ? 120 : 86} height={26} radius={999} testId={`watch-videos-v2-skeleton-recommendation-pill-${pill}`} delay={pill * 35} />
              ))}
            </View>
          </View>

          <View style={{ marginHorizontal: 16, marginBottom: 16, borderRadius: 18, padding: 12, ...baseCardStyle }} data-testid="watch-videos-v2-skeleton-retention" testID="watch-videos-v2-skeleton-retention">
            <SkeletonBlock width="44%" height={16} radius={8} testId="watch-videos-v2-skeleton-retention-title" />
            <SkeletonBlock width="88%" height={12} testId="watch-videos-v2-skeleton-retention-line-1" delay={120} />
            <SkeletonBlock width="70%" height={12} testId="watch-videos-v2-skeleton-retention-line-2" delay={160} />
            <SkeletonBlock width="100%" height={8} radius={999} testId="watch-videos-v2-skeleton-retention-progress" delay={200} />
          </View>
        </>
      ) : null}

      {stage >= 3 ? (
        <>
          {[0, 1].map((railIndex) => (
            <View key={`rail-${railIndex}`} style={{ marginBottom: 18 }} data-testid={`watch-videos-v2-skeleton-rail-${railIndex}`} testID={`watch-videos-v2-skeleton-rail-${railIndex}`}>
              <View style={{ marginHorizontal: 16, marginBottom: 10, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <SkeletonBlock width={180} height={16} radius={8} testId={`watch-videos-v2-skeleton-rail-title-${railIndex}`} />
                <SkeletonBlock width={72} height={22} radius={999} testId={`watch-videos-v2-skeleton-rail-pill-${railIndex}`} delay={80} />
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, paddingHorizontal: 16 }}>
                {[0, 1, 2].map((card) => (
                  <View key={`rail-card-${railIndex}-${card}`} style={{ width: railCardWidth, borderRadius: 16, overflow: 'hidden', ...baseCardStyle }}>
                    <SkeletonBlock width="100%" height={Math.round(railCardWidth * 0.56)} radius={0} testId={`watch-videos-v2-skeleton-rail-card-media-${railIndex}-${card}`} delay={card * 50} />
                    <View style={{ padding: 10, gap: 7 }}>
                      <SkeletonBlock width="88%" height={13} testId={`watch-videos-v2-skeleton-rail-card-title-${railIndex}-${card}`} />
                      <SkeletonBlock width="62%" height={11} testId={`watch-videos-v2-skeleton-rail-card-meta-${railIndex}-${card}`} delay={70} />
                    </View>
                  </View>
                ))}
              </ScrollView>
            </View>
          ))}

          <View style={{ marginHorizontal: 16, marginBottom: 10 }} data-testid="watch-videos-v2-skeleton-grid-header" testID="watch-videos-v2-skeleton-grid-header">
            <SkeletonBlock width={170} height={17} radius={8} testId="watch-videos-v2-skeleton-grid-title" />
          </View>
          <View style={{ marginHorizontal: 16, flexDirection: 'row', flexWrap: 'wrap', columnGap: 8, rowGap: 10 }} data-testid="watch-videos-v2-skeleton-grid" testID="watch-videos-v2-skeleton-grid">
            {[0, 1, 2, 3].map((card) => (
              <View key={`grid-card-${card}`} style={{ width: width >= 980 ? '24%' : width >= 760 ? '48.5%' : '100%', borderRadius: 16, overflow: 'hidden', ...baseCardStyle }}>
                <SkeletonBlock width="100%" height={width < 760 ? 190 : 140} radius={0} testId={`watch-videos-v2-skeleton-grid-card-media-${card}`} delay={card * 50} />
                <View style={{ padding: 10, gap: 7 }}>
                  <SkeletonBlock width="92%" height={13} testId={`watch-videos-v2-skeleton-grid-card-title-${card}`} />
                  <SkeletonBlock width="65%" height={11} testId={`watch-videos-v2-skeleton-grid-card-meta-${card}`} delay={80} />
                </View>
              </View>
            ))}
          </View>
        </>
      ) : null}
    </View>
  );
};
