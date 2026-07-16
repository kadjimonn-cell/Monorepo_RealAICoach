import React, { useCallback } from 'react';
import {
  ActivityIndicator,
  ImageBackground,
  ScrollView,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type Props = {
  colors: any;
  width: number;
  baseCardStyle: any;
  quota: any;
  bootstrap: any;
  featured: any;
  playingVideoId: string;
  watchlistItems: any[];
  continueQueueItems: any[];
  sagaResumeItem: any;
  sagaResumeVideo: any;
  undoFeedbackToast: any;
  undoFeedback: () => void;
  showRecommendationReasons: boolean;
  setShowRecommendationReasons: React.Dispatch<React.SetStateAction<boolean>>;
  applyVisualPreferencePatch: (patch: any) => void;
  playVideo: (video: any, source: string) => void;
  playWatchlistShortcut: () => void;
  playContinueShortcut: () => void;
  playResumeSagaShortcut: () => void;
  categories: string[];
  adminSelectedCategory: string;
  setAdminSelectedCategory: (value: string) => void;
  adminSelectedStylePack: 'cinematic' | 'documentary' | 'creator';
  setAdminSelectedStylePack: (value: 'cinematic' | 'documentary' | 'creator') => void;
  adminApplyingTheme: boolean;
  applyAdminStylePack: () => void;
  regenerateVisualTheme: () => void;
  adminVisualTheme: any;
  observabilitySnapshot: any;
  observabilityLoading: boolean;
  refreshObservability: () => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  searching: boolean;
  activeFeed: string;
  setFeedTab: (value: any) => void;
  selectedSort: string;
  setSelectedSort: (value: any) => void;
  selectedCategory: string;
  setSelectedCategory: (value: string) => void;
  feedTabs: Array<{ key: string; label: string }>;
  sortOptions: Array<{ key: string; label: string; icon: keyof typeof Ionicons.glyphMap }>;
};

export const WatchVideosShell = ({
  colors,
  width,
  baseCardStyle,
  quota,
  bootstrap,
  featured,
  playingVideoId,
  watchlistItems,
  continueQueueItems,
  sagaResumeItem,
  sagaResumeVideo,
  undoFeedbackToast,
  undoFeedback,
  showRecommendationReasons,
  setShowRecommendationReasons,
  applyVisualPreferencePatch,
  playVideo,
  playWatchlistShortcut,
  playContinueShortcut,
  playResumeSagaShortcut,
  categories,
  adminSelectedCategory,
  setAdminSelectedCategory,
  adminSelectedStylePack,
  setAdminSelectedStylePack,
  adminApplyingTheme,
  applyAdminStylePack,
  regenerateVisualTheme,
  adminVisualTheme,
  observabilitySnapshot,
  observabilityLoading,
  refreshObservability,
  searchQuery,
  setSearchQuery,
  searching,
  activeFeed,
  setFeedTab,
  selectedSort,
  setSelectedSort,
  selectedCategory,
  setSelectedCategory,
  feedTabs,
  sortOptions,
}: Props) => {
  const queueInsight = bootstrap?.queue_shortcuts?.queue_insight;
  const usagePercent = quota.limit < 0 ? 0 : Math.min(100, Math.round((Number(quota.used || 0) / Math.max(1, Number(quota.limit || 1))) * 100));
  const incidentTrendPoints = Array.isArray(observabilitySnapshot?.incident_volume_trend_24h?.points)
    ? observabilitySnapshot.incident_volume_trend_24h.points.slice(-12)
    : [];
  const trendMax = Math.max(1, Number(observabilitySnapshot?.incident_volume_trend_24h?.max_incident_events || 0));

  const handleIncidentTimelineCsvExport = useCallback(() => {
    if (typeof window === 'undefined') return;
    const lookbackDays = Number(observabilitySnapshot?.lookback_days || 7);
    const query = Number.isFinite(lookbackDays) ? `?lookback_days=${Math.max(1, Math.min(30, lookbackDays))}` : '';
    const url = `/api/videos/admin/observability/incident-timeline.csv${query}`;
    window.open(url, '_blank', 'noopener,noreferrer');
  }, [observabilitySnapshot?.lookback_days]);

  return (
    <>
      {undoFeedbackToast ? (
        <View
          style={{
            marginHorizontal: 16,
            marginBottom: 12,
            borderRadius: 16,
            borderWidth: 1,
            borderColor: `${colors.primary}77`,
            backgroundColor: `${colors.primary}22`,
            paddingHorizontal: 14,
            paddingVertical: 12,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 10,
          }}
          data-testid="watch-videos-v2-feedback-undo-toast"
          testID="watch-videos-v2-feedback-undo-toast"
        >
          <Text style={{ flex: 1, color: colors.text, fontSize: 12.5, fontWeight: '600' }} data-testid="watch-videos-v2-feedback-undo-text" testID="watch-videos-v2-feedback-undo-text">
            {undoFeedbackToast.nextFeedback === 'like' ? 'Saved: You liked this video' : 'Saved: You disliked this video'}
          </Text>
          <TouchableOpacity
            onPress={undoFeedback}
            style={{
              paddingHorizontal: 12,
              paddingVertical: 7,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: `${colors.primary}88`,
              backgroundColor: colors.card,
            }}
            data-testid="watch-videos-v2-feedback-undo-button"
            testID="watch-videos-v2-feedback-undo-button"
          >
            <Text style={{ color: colors.primary, fontWeight: '700', fontSize: 12 }}>Undo</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <View
        style={{
          marginHorizontal: 16,
          marginBottom: 16,
          borderRadius: 24,
          borderWidth: 1,
          borderColor: `${colors.primary}55`,
          overflow: 'hidden',
          backgroundColor: colors.card,
          shadowColor: 'rgba(0,0,0,0.45)',
          shadowOffset: { width: 0, height: 10 },
          shadowOpacity: 0.32,
          shadowRadius: 20,
          ...baseCardStyle,
        }}
        data-testid="watch-videos-v2-hero"
        testID="watch-videos-v2-hero"
      >
        <ImageBackground
          source={{ uri: featured?.thumbnail_url || undefined }}
          style={{ aspectRatio: width >= 950 ? 16 / 7 : 16 / 9.6, justifyContent: 'flex-end' }}
          imageStyle={{ opacity: 0.94 }}
        >
          <View style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(4,10,20,0.44)' }} />
          <View style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '72%', backgroundColor: 'rgba(3,8,16,0.84)' }} />

          <View style={{ paddingHorizontal: 18, paddingTop: 16, paddingBottom: 18 }}>
            <View
              style={{ alignSelf: 'flex-start', borderRadius: 999, borderWidth: 1, borderColor: 'rgba(157,239,215,0.64)', backgroundColor: 'rgba(16,132,108,0.28)', paddingHorizontal: 10, paddingVertical: 4 }}
              data-testid="watch-videos-v2-hero-kicker"
              testID="watch-videos-v2-hero-kicker"
            >
              <Text style={{ color: 'rgba(218,255,242,0.98)', fontSize: 10.5, fontWeight: '800', letterSpacing: 0.6 }}>
                NOW STREAMING
              </Text>
            </View>

            <Text style={{ marginTop: 10, color: 'rgba(255,255,255,1)', fontSize: 28, fontWeight: '900', lineHeight: 32 }} data-testid="watch-videos-v2-hero-title" testID="watch-videos-v2-hero-title">
              {featured?.title || 'Select a video to begin'}
            </Text>

            <Text
              style={{ marginTop: 8, color: 'rgba(230,236,247,0.9)', fontSize: 12.5, lineHeight: 18 }}
              numberOfLines={2}
              data-testid="watch-videos-v2-hero-description"
              testID="watch-videos-v2-hero-description"
            >
              {featured?.description || 'Dive into curated premium video stories with momentum-first discovery and playback continuity.'}
            </Text>

            <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: `${colors.primary}4A` }}>
                <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 11, fontWeight: '700' }} data-testid="watch-videos-v2-hero-plan-pill" testID="watch-videos-v2-hero-plan-pill">
                  {String(quota.plan || 'free').toUpperCase()}
                </Text>
              </View>
              <View style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.18)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.22)' }}>
                <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 11, fontWeight: '700' }} data-testid="watch-videos-v2-hero-total-pill" testID="watch-videos-v2-hero-total-pill">
                  {`${bootstrap?.total_catalog || 0}+ Videos`}
                </Text>
              </View>
              <View
                style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: 'rgba(26,181,116,0.36)' }}
                data-testid="watch-videos-v2-hero-content-type-badge"
                testID="watch-videos-v2-hero-content-type-badge"
              >
                <Text style={{ color: 'rgba(255,255,255,1)', fontSize: 11.5, fontWeight: '800' }}>VIDEO</Text>
              </View>
            </View>

            <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              <TouchableOpacity
                onPress={() => featured ? playVideo(featured, 'hero_play') : undefined}
                style={{
                  paddingHorizontal: 16,
                  paddingVertical: 10,
                  borderRadius: 999,
                  backgroundColor: colors.primary,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                  borderWidth: 1,
                  borderColor: `${colors.primary}CC`,
                }}
                data-testid="watch-videos-v2-hero-play-button"
                testID="watch-videos-v2-hero-play-button"
              >
                <Ionicons name="play" size={14} color="rgba(255,255,255,1)" />
                <Text style={{ color: 'rgba(255,255,255,1)', fontWeight: '700', fontSize: 12.5 }}>
                  {playingVideoId === featured?.video_id ? 'Opening...' : 'Play now'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={playWatchlistShortcut}
                style={{
                  paddingHorizontal: 15,
                  paddingVertical: 10,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: `${colors.primary}90`,
                  backgroundColor: `${colors.primary}2A`,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid="watch-videos-v2-hero-watchlist-shortcut"
                testID="watch-videos-v2-hero-watchlist-shortcut"
              >
                <Ionicons name="bookmark-outline" size={14} color="rgba(255,255,255,1)" />
                <Text style={{ color: 'rgba(255,255,255,1)', fontWeight: '700', fontSize: 12.5 }}>
                  {`Watchlist (${watchlistItems.length})`}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={playContinueShortcut}
                style={{
                  paddingHorizontal: 15,
                  paddingVertical: 10,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: 'rgba(255,255,255,0.38)',
                  backgroundColor: 'rgba(255,255,255,0.12)',
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid="watch-videos-v2-hero-continue-shortcut"
                testID="watch-videos-v2-hero-continue-shortcut"
              >
                <Ionicons name="play-skip-forward-outline" size={14} color="rgba(255,255,255,1)" />
                <Text style={{ color: 'rgba(255,255,255,1)', fontWeight: '700', fontSize: 12.5 }}>
                  {`Continue Queue (${continueQueueItems.length})`}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={playResumeSagaShortcut}
                style={{
                  paddingHorizontal: 15,
                  paddingVertical: 10,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: 'rgba(249,215,96,0.75)',
                  backgroundColor: 'rgba(249,215,96,0.18)',
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid="watch-videos-v2-hero-resume-saga-shortcut"
                testID="watch-videos-v2-hero-resume-saga-shortcut"
              >
                <Ionicons name="flash-outline" size={14} color="rgba(255,255,255,1)" />
                <Text
                  style={{ color: 'rgba(255,255,255,1)', fontWeight: '700', fontSize: 12.5 }}
                  data-testid="watch-videos-v2-hero-resume-saga-shortcut-text"
                  testID="watch-videos-v2-hero-resume-saga-shortcut-text"
                >
                  {playingVideoId === sagaResumeVideo?.video_id
                    ? 'Opening...'
                    : (sagaResumeItem?.saga_name ? `Resume ${sagaResumeItem.saga_name}` : 'Resume Saga')}
                </Text>
              </TouchableOpacity>
            </View>

            {queueInsight ? (
              <View
                style={{ marginTop: 10, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(146,225,253,0.5)', backgroundColor: 'rgba(17,63,85,0.45)', paddingHorizontal: 10, paddingVertical: 8 }}
                data-testid="watch-videos-v2-hero-queue-insight"
                testID="watch-videos-v2-hero-queue-insight"
              >
                <Text
                  style={{ color: 'rgba(210,244,255,0.98)', fontSize: 11.5, fontWeight: '800' }}
                  data-testid="watch-videos-v2-hero-queue-insight-headline"
                  testID="watch-videos-v2-hero-queue-insight-headline"
                >
                  {queueInsight.headline || 'Binge insight'}
                </Text>
                <Text
                  style={{ marginTop: 3, color: 'rgba(230,240,248,0.88)', fontSize: 11 }}
                  data-testid="watch-videos-v2-hero-queue-insight-reason"
                  testID="watch-videos-v2-hero-queue-insight-reason"
                >
                  {queueInsight.reason || 'Your queue is optimized for minimal drop-off.'}
                </Text>
              </View>
            ) : null}

            {sagaResumeItem ? (
              <View
                style={{ marginTop: 10, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(255,255,255,0.28)', backgroundColor: 'rgba(0,0,0,0.34)', paddingHorizontal: 11, paddingVertical: 9 }}
                data-testid="watch-videos-v2-hero-resume-saga-pin"
                testID="watch-videos-v2-hero-resume-saga-pin"
              >
                <Text
                  style={{ color: 'rgba(255,255,255,0.96)', fontSize: 12, fontWeight: '800' }}
                  data-testid="watch-videos-v2-hero-resume-saga-title"
                  testID="watch-videos-v2-hero-resume-saga-title"
                >
                  {`Resume Saga • ${sagaResumeItem.saga_name || 'Saga Continuity'}`}
                </Text>
                <Text
                  style={{ marginTop: 3, color: 'rgba(255,255,255,0.88)', fontSize: 11.5 }}
                  data-testid="watch-videos-v2-hero-resume-saga-reason"
                  testID="watch-videos-v2-hero-resume-saga-reason"
                >
                  {sagaResumeItem.resume_reason || 'Jump back to your last watched saga chapter.'}
                </Text>
              </View>
            ) : null}
          </View>
        </ImageBackground>
      </View>

      <View style={{ marginHorizontal: 16, marginBottom: 14, ...baseCardStyle, borderRadius: 20, padding: 14 }} data-testid="watch-videos-v2-stats" testID="watch-videos-v2-stats">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <Text style={{ color: colors.text, fontSize: 14, fontWeight: '800' }} data-testid="watch-videos-v2-momentum-title" testID="watch-videos-v2-momentum-title">
            Account Momentum
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11.5 }} data-testid="watch-videos-v2-momentum-subtitle" testID="watch-videos-v2-momentum-subtitle">
            Daily retention controls
          </Text>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ flex: 1, minWidth: 140, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-total-catalog" testID="watch-videos-v2-total-catalog">
            <Text style={{ color: colors.textMuted, fontSize: 11.5 }}>Catalog size</Text>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', marginTop: 3 }}>{bootstrap?.total_catalog || 0}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-total-visible" testID="watch-videos-v2-total-visible">
            <Text style={{ color: colors.textMuted, fontSize: 11.5 }}>Visible to your plan</Text>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', marginTop: 3 }}>{bootstrap?.total_visible || 0}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 140, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-daily-cap" testID="watch-videos-v2-daily-cap">
            <Text style={{ color: colors.textMuted, fontSize: 11.5 }}>Daily watch cap</Text>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: '800', marginTop: 3 }}>
              {quota.limit < 0 ? 'Unlimited' : `${quota.used}/${quota.limit}`}
            </Text>
          </View>
        </View>

        {quota.limit >= 0 ? (
          <View style={{ marginTop: 10 }} data-testid="watch-videos-v2-daily-usage-progress-wrap" testID="watch-videos-v2-daily-usage-progress-wrap">
            <View style={{ height: 8, borderRadius: 999, backgroundColor: `${colors.primary}20`, overflow: 'hidden' }}>
              <View
                style={{ height: '100%', width: `${usagePercent}%`, backgroundColor: usagePercent >= 90 ? colors.error : colors.primary }}
                data-testid="watch-videos-v2-daily-usage-progress-fill"
                testID="watch-videos-v2-daily-usage-progress-fill"
              />
            </View>
            <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 11 }} data-testid="watch-videos-v2-daily-usage-progress-text" testID="watch-videos-v2-daily-usage-progress-text">
              {`${usagePercent}% of today's watch allowance used`}
            </Text>
          </View>
        ) : null}

        <TouchableOpacity
          onPress={() => {
            setShowRecommendationReasons((prev) => {
              const next = !prev;
              applyVisualPreferencePatch({ show_recommendation_reasons: next });
              return next;
            });
          }}
          style={{
            marginTop: 12,
            borderRadius: 999,
            borderWidth: 1,
            borderColor: `${colors.primary}66`,
            backgroundColor: showRecommendationReasons ? `${colors.primary}14` : colors.bgSoft,
            alignSelf: 'flex-start',
            paddingHorizontal: 12,
            paddingVertical: 8,
            flexDirection: 'row',
            alignItems: 'center',
            gap: 7,
          }}
          data-testid="watch-videos-v2-reason-toggle-button"
          testID="watch-videos-v2-reason-toggle-button"
        >
          <Ionicons name={showRecommendationReasons ? 'eye-outline' : 'eye-off-outline'} size={13} color={colors.primary} />
          <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '700' }} data-testid="watch-videos-v2-reason-toggle-text" testID="watch-videos-v2-reason-toggle-text">
            {showRecommendationReasons ? 'Hide recommendation reasons' : 'Show recommendation reasons'}
          </Text>
        </TouchableOpacity>
      </View>

      {bootstrap?.can_admin_visuals ? (
        <View style={{ marginHorizontal: 16, marginBottom: 14, ...baseCardStyle, borderRadius: 20, padding: 12 }} data-testid="watch-videos-v2-admin-visual-theme-card" testID="watch-videos-v2-admin-visual-theme-card">
          <Text style={{ color: colors.text, fontSize: 14.5, fontWeight: '800' }} data-testid="watch-videos-v2-admin-visual-theme-title" testID="watch-videos-v2-admin-visual-theme-title">
            Admin: Visual Theme Studio
          </Text>
          <Text style={{ color: colors.textSec, fontSize: 11.5, marginTop: 4 }}>
            {`Theme cycle: ${adminVisualTheme?.theme_cycle || 'cycle-default'}`}
          </Text>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }}>
            {['all', ...categories.filter((category) => category !== 'all')].map((category) => {
              const active = adminSelectedCategory.toLowerCase() === category.toLowerCase();
              return (
                <TouchableOpacity
                  key={`admin-category-${category}`}
                  onPress={() => setAdminSelectedCategory(category)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? `${colors.primary}66` : colors.border,
                    backgroundColor: active ? `${colors.primary}14` : colors.bgSoft,
                  }}
                  data-testid={`watch-videos-v2-admin-theme-category-${category.toLowerCase().replace(/\s+/g, '-')}`}
                  testID={`watch-videos-v2-admin-theme-category-${category.toLowerCase().replace(/\s+/g, '-')}`}
                >
                  <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11.5, fontWeight: active ? '700' : '500' }}>
                    {category === 'all' ? 'All categories' : category}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }}>
            {(['cinematic', 'documentary', 'creator'] as const).map((pack) => {
              const active = adminSelectedStylePack === pack;
              return (
                <TouchableOpacity
                  key={`admin-pack-${pack}`}
                  onPress={() => setAdminSelectedStylePack(pack)}
                  style={{
                    paddingHorizontal: 10,
                    paddingVertical: 6,
                    borderRadius: 999,
                    borderWidth: 1,
                    borderColor: active ? `${colors.successText}66` : colors.border,
                    backgroundColor: active ? `${colors.successText}14` : colors.bgSoft,
                  }}
                  data-testid={`watch-videos-v2-admin-theme-style-pack-${pack}`}
                  testID={`watch-videos-v2-admin-theme-style-pack-${pack}`}
                >
                  <Text style={{ color: active ? colors.successText : colors.textSec, fontSize: 11.5, fontWeight: active ? '700' : '500' }}>
                    {pack}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            <TouchableOpacity
              onPress={applyAdminStylePack}
              disabled={adminApplyingTheme}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: `${colors.primary}66`,
                backgroundColor: `${colors.primary}14`,
                paddingHorizontal: 12,
                paddingVertical: 8,
                opacity: adminApplyingTheme ? 0.7 : 1,
              }}
              data-testid="watch-videos-v2-admin-theme-apply-style-pack"
              testID="watch-videos-v2-admin-theme-apply-style-pack"
            >
              <Text style={{ color: colors.primary, fontSize: 11.5, fontWeight: '700' }}>
                Apply style pack
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={regenerateVisualTheme}
              disabled={adminApplyingTheme}
              style={{
                borderRadius: 999,
                borderWidth: 1,
                borderColor: `${colors.error}66`,
                backgroundColor: `${colors.error}12`,
                paddingHorizontal: 12,
                paddingVertical: 8,
                opacity: adminApplyingTheme ? 0.7 : 1,
              }}
              data-testid="watch-videos-v2-admin-theme-regenerate"
              testID="watch-videos-v2-admin-theme-regenerate"
            >
              <Text style={{ color: colors.error, fontSize: 11.5, fontWeight: '700' }}>
                Regenerate visual theme
              </Text>
            </TouchableOpacity>

            {adminApplyingTheme ? <ActivityIndicator size="small" color={colors.primary} data-testid="watch-videos-v2-admin-theme-loading" /> : null}
          </View>
        </View>
      ) : null}

      {bootstrap?.can_admin_visuals ? (
        <View
          style={{ marginHorizontal: 16, marginBottom: 14, ...baseCardStyle, borderRadius: 20, padding: 12 }}
          data-testid="watch-videos-v2-admin-observability-card"
          testID="watch-videos-v2-admin-observability-card"
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text
              style={{ color: colors.text, fontSize: 14.5, fontWeight: '800' }}
              data-testid="watch-videos-v2-admin-observability-title"
              testID="watch-videos-v2-admin-observability-title"
            >
              Admin: Watch Videos Observability
            </Text>
            <TouchableOpacity
              onPress={refreshObservability}
              style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5 }}
              data-testid="watch-videos-v2-admin-observability-refresh-button"
              testID="watch-videos-v2-admin-observability-refresh-button"
            >
              <Ionicons name="refresh-outline" size={12} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 11.5, fontWeight: '700' }}>Refresh</Text>
            </TouchableOpacity>
          </View>

          {observabilityLoading ? (
            <View style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="watch-videos-v2-admin-observability-loading" testID="watch-videos-v2-admin-observability-loading">
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={{ color: colors.textSec, fontSize: 11.5 }}>Updating observability snapshot...</Text>
            </View>
          ) : null}

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <View style={{ flex: 1, minWidth: 180, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-admin-observability-p50" testID="watch-videos-v2-admin-observability-p50">
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Watch latency p50</Text>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{`${Number(observabilitySnapshot?.api?.watch_latency_ms?.p50 || 0)} ms`}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 180, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-admin-observability-p95" testID="watch-videos-v2-admin-observability-p95">
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Watch latency p95</Text>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{`${Number(observabilitySnapshot?.api?.watch_latency_ms?.p95 || 0)} ms`}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 180, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-admin-observability-error-rate" testID="watch-videos-v2-admin-observability-error-rate">
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Watch error rate (24h)</Text>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{`${Number(observabilitySnapshot?.api?.watch_error_rate_pct_24h || 0).toFixed(2)}%`}</Text>
            </View>
            <View style={{ flex: 1, minWidth: 180, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, padding: 10 }} data-testid="watch-videos-v2-admin-observability-quota-pressure" testID="watch-videos-v2-admin-observability-quota-pressure">
              <Text style={{ color: colors.textMuted, fontSize: 11 }}>Quota pressure (today)</Text>
              <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800', marginTop: 3 }}>{`${Number(observabilitySnapshot?.risk_signals?.quota_pressure_rate_pct_today || 0).toFixed(2)}%`}</Text>
            </View>
          </View>

          <View style={{ marginTop: 10, borderRadius: 12, borderWidth: 1, borderColor: `${colors.primary}55`, backgroundColor: `${colors.primary}10`, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="watch-videos-v2-admin-observability-footnote" testID="watch-videos-v2-admin-observability-footnote">
            <Text style={{ color: colors.textSec, fontSize: 11 }}>
              {`Calls 24h: ${Number(observabilitySnapshot?.api?.total_calls_24h || 0)} • Active users 24h: ${Number(observabilitySnapshot?.engagement?.active_users_24h || 0)} • Completion: ${Number(observabilitySnapshot?.engagement?.completion_rate_pct_window || 0).toFixed(2)}%`}
            </Text>
          </View>

          <View
            style={{ marginTop: 10, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bgSoft, paddingHorizontal: 10, paddingVertical: 9 }}
            data-testid="watch-videos-v2-admin-incident-timeline-wrap"
            testID="watch-videos-v2-admin-incident-timeline-wrap"
          >
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text
                style={{ color: colors.text, fontSize: 12.2, fontWeight: '800' }}
                data-testid="watch-videos-v2-admin-incident-timeline-title"
                testID="watch-videos-v2-admin-incident-timeline-title"
              >
                Incident Timeline (24h)
              </Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text
                  style={{ color: colors.textSec, fontSize: 10.8 }}
                  data-testid="watch-videos-v2-admin-incident-timeline-count"
                  testID="watch-videos-v2-admin-incident-timeline-count"
                >
                  {`${Number(observabilitySnapshot?.incident_timeline_summary?.spikes_detected || 0)} spike(s)`}
                </Text>
                <TouchableOpacity
                  onPress={handleIncidentTimelineCsvExport}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: `${colors.primary}66`, backgroundColor: `${colors.primary}12`, paddingHorizontal: 8, paddingVertical: 4, flexDirection: 'row', alignItems: 'center', gap: 4 }}
                  data-testid="watch-videos-v2-admin-incident-timeline-csv-export"
                  testID="watch-videos-v2-admin-incident-timeline-csv-export"
                >
                  <Ionicons name="download-outline" size={11} color={colors.primary} />
                  <Text style={{ color: colors.primary, fontSize: 10.5, fontWeight: '700' }}>CSV</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View
              style={{ marginTop: 8, borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, paddingHorizontal: 8, paddingVertical: 7 }}
              data-testid="watch-videos-v2-admin-incident-trend-chart-wrap"
              testID="watch-videos-v2-admin-incident-trend-chart-wrap"
            >
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text
                  style={{ color: colors.textSec, fontSize: 10.5, fontWeight: '700' }}
                  data-testid="watch-videos-v2-admin-incident-trend-chart-title"
                  testID="watch-videos-v2-admin-incident-trend-chart-title"
                >
                  Incident Volume Trend (Last 12h)
                </Text>
                <Text
                  style={{ color: colors.textMuted, fontSize: 10.2 }}
                  data-testid="watch-videos-v2-admin-incident-trend-chart-max"
                  testID="watch-videos-v2-admin-incident-trend-chart-max"
                >
                  {`max ${trendMax}`}
                </Text>
              </View>
              {incidentTrendPoints.length > 0 ? (
                <View style={{ marginTop: 8, flexDirection: 'row', alignItems: 'flex-end', gap: 4, minHeight: 54 }} data-testid="watch-videos-v2-admin-incident-trend-chart-bars" testID="watch-videos-v2-admin-incident-trend-chart-bars">
                  {incidentTrendPoints.map((point: any, idx: number) => {
                    const events = Math.max(0, Number(point?.incident_events || 0));
                    const barHeight = Math.max(4, Math.round((events / trendMax) * 40));
                    const spike = Boolean(point?.incident_spike);
                    return (
                      <View key={`trend-point-${idx}`} style={{ flex: 1, alignItems: 'center', gap: 3 }} data-testid={`watch-videos-v2-admin-incident-trend-point-${idx}`} testID={`watch-videos-v2-admin-incident-trend-point-${idx}`}>
                        <View
                          style={{ width: '100%', maxWidth: 22, height: barHeight, borderRadius: 6, borderWidth: 1, borderColor: spike ? `${colors.error}88` : `${colors.primary}66`, backgroundColor: spike ? `${colors.error}44` : `${colors.primary}33` }}
                          data-testid={`watch-videos-v2-admin-incident-trend-bar-${idx}`}
                          testID={`watch-videos-v2-admin-incident-trend-bar-${idx}`}
                        />
                        <Text style={{ color: colors.textMuted, fontSize: 9.5 }} numberOfLines={1} data-testid={`watch-videos-v2-admin-incident-trend-label-${idx}`} testID={`watch-videos-v2-admin-incident-trend-label-${idx}`}>
                          {String(point?.hour_label || '').slice(0, 2)}h
                        </Text>
                      </View>
                    );
                  })}
                </View>
              ) : (
                <Text style={{ marginTop: 8, color: colors.textSec, fontSize: 10.5 }} data-testid="watch-videos-v2-admin-incident-trend-chart-empty" testID="watch-videos-v2-admin-incident-trend-chart-empty">
                  Trend data will appear after observability telemetry accumulates.
                </Text>
              )}
            </View>

            {Array.isArray(observabilitySnapshot?.incident_timeline) && observabilitySnapshot.incident_timeline.length > 0 ? (
              <View style={{ marginTop: 8, gap: 8 }} data-testid="watch-videos-v2-admin-incident-timeline-list" testID="watch-videos-v2-admin-incident-timeline-list">
                {observabilitySnapshot.incident_timeline.slice(0, 4).map((incident: any, idx: number) => {
                  const severity = String(incident?.severity || 'medium').toLowerCase();
                  const severityColor = severity === 'high' ? colors.error : (severity === 'low' ? colors.successText : colors.warningText);
                  const metrics = incident?.metrics || {};
                  const actions = Array.isArray(incident?.suggested_actions) ? incident.suggested_actions.slice(0, 2) : [];
                  const hourBucket = String(incident?.hour_bucket || '').replace('T', ' ').slice(0, 16);
                  return (
                    <View
                      key={`incident-timeline-${idx}`}
                      style={{ borderRadius: 10, borderWidth: 1, borderColor: `${severityColor}66`, backgroundColor: `${severityColor}12`, paddingHorizontal: 9, paddingVertical: 8 }}
                      data-testid={`watch-videos-v2-admin-incident-timeline-item-${idx}`}
                      testID={`watch-videos-v2-admin-incident-timeline-item-${idx}`}
                    >
                      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7 }}>
                        <Text style={{ color: colors.text, fontSize: 11.4, fontWeight: '800' }} data-testid={`watch-videos-v2-admin-incident-timeline-item-title-${idx}`} testID={`watch-videos-v2-admin-incident-timeline-item-title-${idx}`}>
                          {String(incident?.title || 'Incident spike detected')}
                        </Text>
                        <View style={{ borderRadius: 999, borderWidth: 1, borderColor: `${severityColor}66`, backgroundColor: `${severityColor}15`, paddingHorizontal: 8, paddingVertical: 3 }} data-testid={`watch-videos-v2-admin-incident-timeline-item-severity-${idx}`} testID={`watch-videos-v2-admin-incident-timeline-item-severity-${idx}`}>
                          <Text style={{ color: severityColor, fontSize: 10.2, fontWeight: '800' }}>{severity.toUpperCase()}</Text>
                        </View>
                      </View>

                      <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 10.8 }} data-testid={`watch-videos-v2-admin-incident-timeline-item-hour-${idx}`} testID={`watch-videos-v2-admin-incident-timeline-item-hour-${idx}`}>
                        {hourBucket || 'Recent window'}
                      </Text>

                      <Text style={{ marginTop: 4, color: colors.textSec, fontSize: 10.7 }} data-testid={`watch-videos-v2-admin-incident-timeline-item-metrics-${idx}`} testID={`watch-videos-v2-admin-incident-timeline-item-metrics-${idx}`}>
                        {`Err ${Number(metrics?.error_rate_pct || 0).toFixed(2)}% • Watch p95 ${Number(metrics?.watch_p95_ms || 0)}ms • 429 ${Number(metrics?.quota_rejections || 0)}`}
                      </Text>

                      {actions.map((action: string, actionIdx: number) => (
                        <Text
                          key={`incident-${idx}-action-${actionIdx}`}
                          style={{ marginTop: 4, color: colors.text, fontSize: 10.4 }}
                          data-testid={`watch-videos-v2-admin-incident-timeline-item-action-${idx}-${actionIdx}`}
                          testID={`watch-videos-v2-admin-incident-timeline-item-action-${idx}-${actionIdx}`}
                        >
                          {`• ${action}`}
                        </Text>
                      ))}
                    </View>
                  );
                })}
              </View>
            ) : (
              <Text style={{ marginTop: 8, color: colors.textSec, fontSize: 10.9 }} data-testid="watch-videos-v2-admin-incident-timeline-empty" testID="watch-videos-v2-admin-incident-timeline-empty">
                No major spikes detected in the last 24 hours.
              </Text>
            )}
          </View>
        </View>
      ) : null}

      <View style={{ marginHorizontal: 16, marginBottom: 14, ...baseCardStyle, borderRadius: 20, padding: 12 }} data-testid="watch-videos-v2-filters-card" testID="watch-videos-v2-filters-card">
        <View style={{ marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text style={{ color: colors.text, fontSize: 13.5, fontWeight: '800' }} data-testid="watch-videos-v2-filters-title" testID="watch-videos-v2-filters-title">
            Discovery Console
          </Text>
          <Text style={{ color: colors.textMuted, fontSize: 11.5 }} data-testid="watch-videos-v2-filters-subtitle" testID="watch-videos-v2-filters-subtitle">
            Search • sort • explore
          </Text>
        </View>

        <View style={{
          borderRadius: 12,
          borderWidth: 1,
          borderColor: colors.border,
          backgroundColor: colors.bgSoft,
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          paddingHorizontal: 12,
          paddingVertical: 10,
        }} data-testid="watch-videos-v2-search-wrap" testID="watch-videos-v2-search-wrap">
          <Ionicons name="search-outline" size={16} color={colors.textMuted} />
          <TextInput
            value={searchQuery}
            onChangeText={setSearchQuery}
            placeholder="Search title, studio, tags, category"
            placeholderTextColor={colors.textMuted}
            style={{ flex: 1, color: colors.text, fontSize: 13.5 }}
            data-testid="watch-videos-v2-search-input"
            testID="watch-videos-v2-search-input"
          />
          {searching ? <ActivityIndicator size="small" color={colors.primary} data-testid="watch-videos-v2-search-loading" testID="watch-videos-v2-search-loading" /> : null}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }} data-testid="watch-videos-v2-tabs-scroll" testID="watch-videos-v2-tabs-scroll">
          {feedTabs.map((tab) => {
            const active = tab.key === activeFeed;
            return (
              <TouchableOpacity
                key={tab.key}
                onPress={() => setFeedTab(tab.key)}
                style={{
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: active ? `${colors.primary}66` : colors.border,
                  backgroundColor: active ? `${colors.primary}14` : colors.bgSoft,
                }}
                data-testid={`watch-videos-v2-tab-${tab.key}`}
                testID={`watch-videos-v2-tab-${tab.key}`}
              >
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 12, fontWeight: active ? '700' : '500' }}>{tab.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }} data-testid="watch-videos-v2-sort-scroll" testID="watch-videos-v2-sort-scroll">
          {sortOptions.map((option) => {
            const active = option.key === selectedSort;
            return (
              <TouchableOpacity
                key={option.key}
                onPress={() => setSelectedSort(option.key)}
                style={{
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: active ? `${colors.primary}66` : colors.border,
                  backgroundColor: active ? `${colors.primary}12` : colors.bgSoft,
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 6,
                }}
                data-testid={`watch-videos-v2-sort-${option.key}`}
                testID={`watch-videos-v2-sort-${option.key}`}
              >
                <Ionicons name={option.icon} size={13} color={active ? colors.primary : colors.textMuted} />
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11.5, fontWeight: active ? '700' : '500' }}>{option.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }} data-testid="watch-videos-v2-categories-scroll" testID="watch-videos-v2-categories-scroll">
          {categories.map((category) => {
            const normalized = category.toLowerCase().replace(/\s+/g, '-');
            const active = selectedCategory.toLowerCase() === category.toLowerCase();
            return (
              <TouchableOpacity
                key={category}
                onPress={() => setSelectedCategory(category)}
                style={{
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderRadius: 999,
                  borderWidth: 1,
                  borderColor: active ? `${colors.primary}66` : colors.border,
                  backgroundColor: active ? `${colors.primary}13` : colors.bgSoft,
                }}
                data-testid={`watch-videos-v2-category-${normalized}`}
                testID={`watch-videos-v2-category-${normalized}`}
              >
                <Text style={{ color: active ? colors.primary : colors.textSec, fontSize: 11.5, fontWeight: active ? '700' : '500' }}>
                  {category === 'all' ? 'All categories' : category}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>
    </>
  );
};
