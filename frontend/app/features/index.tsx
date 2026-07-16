import React, { useMemo, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, TextInput, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '../../src/context/ThemeContext';
import { FeatureIndexSkeleton, usePageReady } from '../../src/components/SkeletonLoaders';
import { useGlobalPlatformState } from '../../src/hooks/useGlobalPlatformState';
import { useLiveQuery } from '../../src/hooks/useLiveQuery';
import { useTranslation } from '../../src/hooks/useTranslation';
import GpsLabelBlocker from '../../src/components/GpsLabelBlocker';
import { GpsDataStatusCard } from '../../src/components/GpsDataStatusCard';
import { useAuth } from '../../src/context/AuthContext';
import api from '../../src/services/api';
import { FeatureLifecycleDrawer } from '../../src/components/features/FeatureLifecycleDrawer';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

export default function FeaturesHub() {
  const pageReady = usePageReady();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { colors } = useTheme();
  const { user } = useAuth();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const normalizeFeatureDescription = useCallback((feature: any) => {
    const raw = String(feature?.description || '').trim();
    if (!raw || ['description', 'subtitle'].includes(raw.toLowerCase())) {
      return tx('features.card.descriptionFallback', 'Open this feature and continue your workflow with AI-guided support.');
    }
    return raw;
  }, [tx]);
  const {
    state: gpsState,
    counts,
    strictLabel,
    getMissingLabels,
    loading: gpsLoading,
    error: gpsError,
    refetch: gpsRefetch,
    diagnostics: gpsDiagnostics,
  } = useGlobalPlatformState();
  const {
    data: hubInsights,
    loading: hubInsightsLoading,
    error: hubInsightsError,
    refetch: hubInsightsRefetch,
  } = useLiveQuery('/features/hub-insights', { entity: 'features_hub_insights', pollInterval: 30000 });

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [lifecycleVisible, setLifecycleVisible] = useState(false);
  const [lifecycleLoading, setLifecycleLoading] = useState(false);
  const [lifecycleError, setLifecycleError] = useState('');
  const [lifecycleAudit, setLifecycleAudit] = useState<any>(null);

  const C = useMemo(
    () => ({
      bg: colors.bg,
      card: colors.card,
      bgSoft: colors.bgSoft,
      surface: colors.surface,
      text: colors.text,
      textMuted: colors.textMuted,
      textSec: colors.textSec,
      border: colors.border,
      primary: colors.primary,
      primaryText: colors.primaryText,
      success: colors.success,
      successText: colors.successText,
      warning: colors.warning,
      warningText: colors.warningText,
      error: colors.error,
    }),
    [colors],
  );
  const styles = useMemo(() => createStyles(C), [C]);

  const features = useMemo(
    () => (gpsState.features || []).filter((f) => f.enabled !== false && f.soft_deactivated !== true),
    [gpsState.features],
  );
  const categories = useMemo(() => {
    const values = Array.from(new Set(features.map((f) => String(f.category || 'general'))));
    return ['all', ...values];
  }, [features]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return features.filter((feature) => {
      const matchCategory = selectedCategory === 'all' || feature.category === selectedCategory;
      const matchQuery =
        !q ||
        feature.title.toLowerCase().includes(q) ||
        normalizeFeatureDescription(feature).toLowerCase().includes(q) ||
        (feature.feature_id || '').toLowerCase().includes(q);
      return matchCategory && matchQuery;
    });
  }, [features, normalizeFeatureDescription, selectedCategory, searchQuery]);

  const topCategoryCards = useMemo(() => {
    const countsByCategory = features.reduce((acc: Record<string, number>, item) => {
      const key = String(item.category || 'general');
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
    return Object.entries(countsByCategory)
      .map(([key, value]) => ({ key, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 4);
  }, [features]);

  const usageSummary = hubInsights?.usage_summary || {};
  const dailySpotlight = Array.isArray(hubInsights?.daily_spotlight) ? hubInsights.daily_spotlight : [];
  const recentlyUsed = Array.isArray(hubInsights?.recently_used) ? hubInsights.recently_used : [];
  const subscriptionPlan = String(hubInsights?.subscription_plan || 'free').toUpperCase();
  const activePlan = subscriptionPlan.toLowerCase();
  const isAdmin = hasAdminConsoleVisibility(user as any);

  const unlockedForPlanCount = useMemo(() => {
    if (activePlan === 'premium') return features.length;
    return features.filter((feature) => !Boolean(feature.premium)).length;
  }, [activePlan, features]);

  const openLifecycleDrawer = async () => {
    setLifecycleVisible(true);
    if (lifecycleAudit || lifecycleLoading) return;
    setLifecycleLoading(true);
    setLifecycleError('');
    try {
      const response = await api.get('/admin/features/lifecycle-audit', { silentLoading: true });
      setLifecycleAudit(response.data);
    } catch (error: any) {
      setLifecycleError(String(error?.response?.data?.detail || error?.message || tx('features.lifecycle.error', 'Lifecycle audit unavailable.')));
    } finally {
      setLifecycleLoading(false);
    }
  };

  const requiredFeatureIndexLabelKeys = [
    'features.header.title',
    'features.header.count_label',
    'features.header.subtitle',
    'features.search.placeholder',
    'features.category.all',
    'features.results.label',
    'features.empty.description',
    'features.empty.title',
    'features.empty.subtitle',
  ];
  const missingFeatureLabels = getMissingLabels(requiredFeatureIndexLabelKeys);

  if (!pageReady) return <FeatureIndexSkeleton />;
  if (gpsLoading && !gpsError) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, paddingHorizontal: 16, paddingTop: 20 }}>
        <GpsDataStatusCard
          surfaceName="features"
          loading={gpsLoading}
          error={gpsError}
          onRetry={() => void gpsRefetch()}
          colors={{
            bg: C.bg,
            card: C.card,
            text: C.text,
            textSec: C.textSec,
            textMuted: C.textMuted,
            border: C.border,
            borderSoft: C.border,
            primary: C.primary,
            error: colors.error,
            success: colors.success,
            warning: colors.warning,
          }}
          diagnostics={gpsDiagnostics}
          testIdPrefix="features"
        />
      </View>
    );
  }
  if (missingFeatureLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live') {
    return <GpsLabelBlocker surfaceName="feature-index" missingKeys={missingFeatureLabels} colors={C} />;
  }

  const pad = width >= 1024 ? 24 : 16;
  const cardWidth = width >= 900 ? '31.8%' : width >= 620 ? '48.5%' : '100%';

  return (
    <SafeAreaView style={styles.container} edges={['top']} data-testid="features-screen" testID="features-screen">
      {gpsError ? (
        <View
          style={{ paddingHorizontal: 16, paddingTop: 12 }}
          data-testid="features-inline-gps-status-wrapper"
          testID="features-inline-gps-status-wrapper"
        >
          <GpsDataStatusCard
            surfaceName="features"
            loading={false}
            error={gpsError}
            onRetry={() => void gpsRefetch()}
            colors={{
              bg: C.bg,
              card: C.card,
              text: C.text,
              textSec: C.textSec,
              textMuted: C.textMuted,
              border: C.border,
              borderSoft: C.border,
              primary: C.primary,
              error: colors.error,
              success: colors.success,
              warning: colors.warning,
            }}
            diagnostics={gpsDiagnostics}
            testIdPrefix="features"
          />
        </View>
      ) : null}

      <View style={styles.header} data-testid="features-header" testID="features-header">
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => router.back()}
          data-testid="features-back-button"
          testID="features-back-button"
        >
          <Ionicons name="arrow-back" size={20} color={C.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} data-testid="features-header-title" testID="features-header-title">
          {strictLabel('features.header.title')}
        </Text>
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => {
            void gpsRefetch();
            void hubInsightsRefetch();
          }}
          data-testid="features-refresh-button"
          testID="features-refresh-button"
        >
          <Ionicons name="refresh" size={18} color={C.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }} showsVerticalScrollIndicator={false}>
        <View style={[styles.commandDeck, { marginHorizontal: pad, marginTop: 16 }]} data-testid="features-command-deck" testID="features-command-deck">
          <View style={{ flexDirection: width >= 860 ? 'row' : 'column', justifyContent: 'space-between', gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={styles.commandDeckTitle} data-testid="features-command-deck-title" testID="features-command-deck-title">
                {tx('features.commandDeck.title', 'Feature Command Center')}
              </Text>
              <Text style={styles.commandDeckSubtitle} data-testid="features-command-deck-subtitle" testID="features-command-deck-subtitle">
                {tx('features.commandDeck.subtitle', 'Discover high-impact features, continue recently used flows, and launch a daily feature sprint.')}
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <View style={styles.planChip} data-testid="features-plan-chip" testID="features-plan-chip">
                <Text style={styles.planChipText}>{subscriptionPlan}</Text>
              </View>
              <View style={styles.statusChip} data-testid="features-command-status-chip" testID="features-command-status-chip">
                <Text style={styles.statusChipText}>{hubInsightsLoading ? tx('features.commandDeck.syncing', 'SYNCING') : tx('features.commandDeck.live', 'LIVE')}</Text>
              </View>
            </View>
          </View>

          <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="features-command-kpis" testID="features-command-kpis">
            {[
              { id: 'sessions', label: tx('features.commandDeck.sessions30d', 'Sessions (30d)'), value: Number(usageSummary.sessions_30d || 0), icon: 'pulse-outline' },
              { id: 'active-days', label: tx('features.commandDeck.activeDays', 'Active Days'), value: Number(usageSummary.active_days_30d || 0), icon: 'calendar-outline' },
              { id: 'used-features', label: tx('features.commandDeck.usedFeatures', 'Used Features'), value: Number(usageSummary.used_features_30d || 0), icon: 'apps-outline' },
              { id: 'favorite-category', label: tx('features.commandDeck.favoriteCategory', 'Favorite Category'), value: tx(`features.category.${String(usageSummary.favorite_category || 'general')}`, String(usageSummary.favorite_category || 'general').replace(/-/g, ' ')), icon: 'star-outline' },
            ].map((metric) => (
              <View key={metric.id} style={styles.metricCard} data-testid={`features-command-kpi-${metric.id}`} testID={`features-command-kpi-${metric.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={metric.icon as any} size={13} color={C.primary} />
                  <Text style={styles.metricLabel}>{metric.label}</Text>
                </View>
                <Text style={styles.metricValue}>{metric.value}</Text>
              </View>
            ))}
          </View>

          {hubInsightsError ? (
            <Text style={styles.commandErrorText} data-testid="features-command-deck-error" testID="features-command-deck-error">
              {tx('features.commandDeck.error', 'Insights feed delayed. Core features remain fully available.')}
            </Text>
          ) : null}

          <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            <TouchableOpacity
              style={styles.sprintButton}
              onPress={() => router.push(((dailySpotlight[0] && dailySpotlight[0].route) || '/feature-gallery') as any)}
              data-testid="features-start-daily-sprint-button"
              testID="features-start-daily-sprint-button"
            >
              <Ionicons name="rocket-outline" size={14} color={C.primaryText} />
              <Text style={styles.sprintButtonText}>{tx('features.commandDeck.startSprint', 'Start Daily Feature Sprint')}</Text>
            </TouchableOpacity>
            {isAdmin ? (
              <TouchableOpacity
                style={styles.lifecycleButton}
                onPress={openLifecycleDrawer}
                data-testid="features-lifecycle-open-button"
                testID="features-lifecycle-open-button"
              >
                <Ionicons name="git-branch-outline" size={14} color={C.primary} />
                <Text style={styles.lifecycleButtonText}>{tx('features.lifecycle.open', 'Feature Lifecycle')}</Text>
              </TouchableOpacity>
            ) : null}
          </View>

          <Text style={styles.planLegendText} data-testid="features-plan-legend" testID="features-plan-legend">
            {tx('features.commandDeck.planLegend', 'Plan badges on cards show unlock visibility across Free / Basic / Premium.')}
          </Text>
        </View>

        <View style={[styles.signalBoard, { marginHorizontal: pad }]} data-testid="features-signal-board" testID="features-signal-board">
          <Text style={styles.signalBoardTitle} data-testid="features-signal-board-title" testID="features-signal-board-title">
            {tx('features.signalBoard.title', 'Feature Portfolio Signal Board')}
          </Text>
          <Text style={styles.signalBoardSubtitle} data-testid="features-signal-board-subtitle" testID="features-signal-board-subtitle">
            {tx('features.signalBoard.subtitle', 'Quickly scan catalog coverage, unlocked scope, and dominant feature categories for this account.')}
          </Text>

          <View style={{ marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {[
              { id: 'catalog', label: tx('features.signalBoard.catalog', 'Catalog size'), value: features.length, icon: 'apps-outline' },
              { id: 'unlocked', label: tx('features.signalBoard.unlocked', 'Unlocked for plan'), value: unlockedForPlanCount, icon: 'lock-open-outline' },
              { id: 'spotlight', label: tx('features.signalBoard.spotlight', 'Daily spotlight'), value: dailySpotlight.length, icon: 'flash-outline' },
              { id: 'recent', label: tx('features.signalBoard.recent', 'Recently used'), value: recentlyUsed.length, icon: 'time-outline' },
            ].map((signal) => (
              <View key={signal.id} style={styles.signalCard} data-testid={`features-signal-card-${signal.id}`} testID={`features-signal-card-${signal.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={signal.icon as any} size={13} color={C.primary} />
                  <Text style={styles.signalCardLabel}>{signal.label}</Text>
                </View>
                <Text style={styles.signalCardValue}>{signal.value}</Text>
              </View>
            ))}
          </View>

          {topCategoryCards.length > 0 ? (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 8, marginTop: 10 }}
              data-testid="features-signal-categories"
              testID="features-signal-categories"
            >
              {topCategoryCards.map((entry, idx) => (
                <TouchableOpacity
                  key={entry.key}
                  style={styles.categorySignalChip}
                  onPress={() => setSelectedCategory(entry.key)}
                  data-testid={`features-signal-category-${idx}`}
                  testID={`features-signal-category-${idx}`}
                >
                  <Ionicons name="funnel-outline" size={12} color={C.primary} />
                  <Text style={styles.categorySignalChipText}>{tx(`features.category.${entry.key}`, entry.key.replace(/-/g, ' '))}</Text>
                  <Text style={styles.categorySignalChipCount}>{entry.value}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          ) : null}
        </View>

        {dailySpotlight.length > 0 ? (
          <View style={{ marginTop: 14, paddingHorizontal: pad }} data-testid="features-daily-spotlight" testID="features-daily-spotlight">
            <Text style={styles.sectionHeading}>{tx('features.spotlight.title', 'Daily Spotlight')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 }}>
              {dailySpotlight.map((spot: any, idx: number) => (
                <TouchableOpacity
                  key={spot.feature_id || idx}
                  style={[styles.spotlightCard, { width: cardWidth as any }]}
                  onPress={() => router.push((spot.route || '/feature-gallery') as any)}
                  data-testid={`features-spotlight-card-${idx}`}
                  testID={`features-spotlight-card-${idx}`}
                >
                  <Text style={styles.spotlightTitle}>{String(spot.title || 'Feature')}</Text>
                  <Text style={styles.spotlightMeta}>{tx(`features.category.${String(spot.category || 'general')}`, String(spot.category || 'general'))}</Text>
                  <Text style={styles.spotlightPopularity}>{tx('features.spotlight.popularity', 'Global popularity')}: {Number(spot.global_popularity || 0)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ) : null}

        {recentlyUsed.length > 0 ? (
          <View style={{ marginTop: 14 }} data-testid="features-recently-used" testID="features-recently-used">
            <Text style={[styles.sectionHeading, { paddingHorizontal: pad }]}>{tx('features.recent.title', 'Continue Recently Used')}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: pad, gap: 8, marginTop: 8 }}>
              {recentlyUsed.map((item: any, idx: number) => (
                <TouchableOpacity
                  key={item.feature_id || idx}
                  style={styles.recentChip}
                  onPress={() => router.push((item.route || '/feature-gallery') as any)}
                  data-testid={`features-recent-chip-${idx}`}
                  testID={`features-recent-chip-${idx}`}
                >
                  <Ionicons name={(item.icon as any) || 'apps'} size={13} color={C.primary} />
                  <Text style={styles.recentChipText}>{String(item.title || item.feature_id || 'Feature')}</Text>
                  <Text style={styles.recentChipMeta}>{Number(item.usage_count_30d || 0)}x</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        ) : null}

        <View style={{ paddingHorizontal: pad, paddingTop: 16, paddingBottom: 10 }}>
          <Text style={styles.heroTitle} data-testid="features-count-title" testID="features-count-title">
            {counts.features} {strictLabel('features.header.count_label')}
          </Text>
          <Text style={styles.heroSubtitle} data-testid="features-count-subtitle" testID="features-count-subtitle">
            {strictLabel('features.header.subtitle') || tx('features.header.subtitle.fallback', 'Explore the full AI capabilities catalog')}
          </Text>
        </View>

        <View style={[styles.searchWrap, { marginHorizontal: pad }]}>
          <Ionicons name="search" size={18} color={C.textMuted} />
          <TextInput
            data-testid="features-search-input"
            testID="features-search-input"
            style={styles.searchInput}
            placeholder={strictLabel('features.search.placeholder') || tx('features.search.placeholder.fallback', 'Search features')}
            placeholderTextColor={C.textMuted}
            value={searchQuery}
            onChangeText={setSearchQuery}
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity data-testid="features-search-clear" testID="features-search-clear" onPress={() => setSearchQuery('')}>
              <Ionicons name="close-circle" size={18} color={C.textMuted} />
            </TouchableOpacity>
          )}
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: pad, gap: 8, marginTop: 12 }}>
          {categories.map((category) => {
            const active = selectedCategory === category;
            const count = category === 'all' ? features.length : features.filter((f) => f.category === category).length;
            const labelText = category === 'all' ? strictLabel('features.category.all') : category.replace(/-/g, ' ');
            return (
              <TouchableOpacity
                key={category}
                data-testid={`features-category-${category}`}
                testID={`features-category-${category}`}
                style={[styles.chip, active ? styles.chipActive : null]}
                onPress={() => setSelectedCategory(category)}
              >
                <Text style={[styles.chipText, active ? styles.chipTextActive : null]}>
                  {labelText} ({count})
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <Text style={[styles.resultsText, { paddingHorizontal: pad }]} data-testid="features-results-count" testID="features-results-count">
          {filtered.length} {strictLabel('features.results.label')}
        </Text>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, paddingHorizontal: pad }}>
          {filtered.map((feature) => (
            <TouchableOpacity
              key={feature.feature_id}
              style={[styles.card, { width: cardWidth as any }]}
              data-testid={`features-card-${feature.feature_id}`}
              testID={`features-card-${feature.feature_id}`}
              onPress={() => router.push((feature.route || '/welcome') as any)}
              activeOpacity={0.8}
            >
              <View style={styles.cardTop}>
                <View style={[styles.iconWrap, { backgroundColor: `${feature.color || C.primary}20` }]}>
                  <Ionicons name={(feature.icon as any) || 'apps'} size={18} color={feature.color || C.primary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{feature.title}</Text>
                  <Text style={styles.cardCategory}>{tx(`features.category.${String(feature.category || 'general')}`, String(feature.category || 'general').replace(/-/g, ' '))}</Text>
                </View>
              </View>
              <Text style={styles.cardDesc}>{normalizeFeatureDescription(feature)}</Text>

              <View style={styles.planBadgesRow} data-testid={`features-plan-badges-${feature.feature_id}`} testID={`features-plan-badges-${feature.feature_id}`}>
                {(['free', 'basic', 'premium'] as const).map((planTier) => {
                  const unlocked = planTier === 'premium' ? true : !Boolean(feature.premium);
                  const active = activePlan === planTier;
                  return (
                    <View
                      key={planTier}
                      style={[
                        styles.planBadge,
                        unlocked ? styles.planBadgeUnlocked : styles.planBadgeLocked,
                        active ? styles.planBadgeActive : null,
                      ]}
                      data-testid={`features-plan-badge-${feature.feature_id}-${planTier}`}
                      testID={`features-plan-badge-${feature.feature_id}-${planTier}`}
                    >
                      <Ionicons name={unlocked ? 'checkmark-circle' : 'lock-closed'} size={10} color={unlocked ? C.successText : C.warningText} />
                      <Text style={[styles.planBadgeText, unlocked ? styles.planBadgeTextUnlocked : styles.planBadgeTextLocked]}>{tx(`subscriptionPlans.plan.${planTier}.name`, planTier.toUpperCase())}</Text>
                    </View>
                  );
                })}
              </View>
            </TouchableOpacity>
          ))}
        </View>

        {filtered.length === 0 && (
          <View style={styles.emptyState} data-testid="features-empty" testID="features-empty">
            <Ionicons name="search-outline" size={44} color={C.textMuted} />
            <Text style={styles.emptyTitle}>{tx('features.empty.title', 'No features found')}</Text>
            <Text style={styles.emptySubtitle}>{tx('features.empty.subtitle', 'Try a different search term or category.')}</Text>
          </View>
        )}
      </ScrollView>

      <FeatureLifecycleDrawer
        visible={lifecycleVisible}
        onClose={() => setLifecycleVisible(false)}
        audit={lifecycleAudit}
        loading={lifecycleLoading}
        error={lifecycleError}
        width={width}
        fallbackActiveCount={counts.features}
      />
    </SafeAreaView>
  );
}

const createStyles = (C: any) =>
  StyleSheet.create({
    container: { flex: 1, backgroundColor: C.bg },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingVertical: 12,
      backgroundColor: C.card,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    backButton: {
      width: 40,
      height: 40,
      borderRadius: 20,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: C.bgSoft,
    },
    headerTitle: { fontSize: 17, fontWeight: '800', color: C.text },
    heroTitle: { fontSize: 28, fontWeight: '800', color: C.text, letterSpacing: -0.6 },
    heroSubtitle: { marginTop: 4, fontSize: 13, color: C.textSec, lineHeight: 19 },
    commandDeck: {
      borderRadius: 18,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      padding: 14,
    },
    commandDeckTitle: { fontSize: 18, fontWeight: '900', color: C.text },
    commandDeckSubtitle: { marginTop: 4, fontSize: 12, color: C.textSec, lineHeight: 18 },
    planChip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: `${C.primary}66`,
      backgroundColor: `${C.primary}15`,
      paddingHorizontal: 10,
      paddingVertical: 5,
    },
    planChipText: { color: C.primary, fontSize: 10, fontWeight: '800' },
    statusChip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bgSoft,
      paddingHorizontal: 10,
      paddingVertical: 5,
    },
    statusChipText: { color: C.textMuted, fontSize: 10, fontWeight: '800' },
    metricCard: {
      flex: 1,
      minWidth: 130,
      borderRadius: 10,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bgSoft,
      padding: 10,
    },
    metricLabel: { fontSize: 10, color: C.textMuted, fontWeight: '700' },
    metricValue: { marginTop: 6, fontSize: 18, fontWeight: '900', color: C.text, textTransform: 'capitalize' },
    sprintButton: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.primary,
      backgroundColor: C.primary,
      paddingHorizontal: 14,
      paddingVertical: 8,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    sprintButtonText: { color: C.primaryText, fontSize: 11, fontWeight: '800' },
    lifecycleButton: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: `${C.primary}66`,
      backgroundColor: `${C.primary}12`,
      paddingHorizontal: 14,
      paddingVertical: 8,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    lifecycleButtonText: { color: C.primary, fontSize: 11, fontWeight: '800' },
    planLegendText: { marginTop: 8, color: C.textMuted, fontSize: 11 },
    signalBoard: {
      marginTop: 12,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      padding: 14,
    },
    signalBoardTitle: { fontSize: 16, fontWeight: '900', color: C.text },
    signalBoardSubtitle: { marginTop: 4, fontSize: 12, color: C.textSec, lineHeight: 18 },
    signalCard: {
      flex: 1,
      minWidth: 130,
      borderRadius: 11,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surface,
      padding: 10,
    },
    signalCardLabel: { fontSize: 10, color: C.textMuted, fontWeight: '700' },
    signalCardValue: { marginTop: 6, fontSize: 20, color: C.text, fontWeight: '900' },
    categorySignalChip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bgSoft,
      paddingHorizontal: 11,
      paddingVertical: 7,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
    },
    categorySignalChipText: { color: C.textSec, fontSize: 11, fontWeight: '700', textTransform: 'capitalize' },
    categorySignalChipCount: { color: C.primary, fontSize: 11, fontWeight: '800' },
    commandErrorText: { marginTop: 8, color: C.error, fontSize: 11, fontWeight: '700' },
    sectionHeading: { fontSize: 14, fontWeight: '800', color: C.text },
    spotlightCard: {
      borderRadius: 12,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      padding: 12,
      minHeight: 94,
    },
    spotlightTitle: { color: C.text, fontSize: 13, fontWeight: '800' },
    spotlightMeta: { marginTop: 3, color: C.textMuted, fontSize: 11, textTransform: 'capitalize' },
    spotlightPopularity: { marginTop: 7, color: C.textSec, fontSize: 11 },
    recentChip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      paddingHorizontal: 12,
      paddingVertical: 8,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 7,
    },
    recentChipText: { color: C.text, fontSize: 12, fontWeight: '700' },
    recentChipMeta: { color: C.textMuted, fontSize: 11 },
    searchWrap: {
      borderRadius: 12,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      paddingHorizontal: 14,
      flexDirection: 'row',
      alignItems: 'center',
    },
    searchInput: { flex: 1, paddingVertical: 12, marginLeft: 10, color: C.text, fontSize: 14 },
    chip: {
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bgSoft,
      paddingHorizontal: 12,
      paddingVertical: 8,
    },
    chipActive: { backgroundColor: C.primary, borderColor: C.primary },
    chipText: { color: C.textMuted, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' },
    chipTextActive: { color: C.primaryText },
    resultsText: { marginTop: 12, marginBottom: 12, color: C.textMuted, fontSize: 12, fontWeight: '600' },
    card: {
      borderRadius: 16,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.card,
      padding: 14,
      minHeight: 150,
    },
    cardTop: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
    iconWrap: { width: 38, height: 38, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
    cardTitle: { color: C.text, fontSize: 14, fontWeight: '700' },
    cardCategory: { marginTop: 2, color: C.textMuted, fontSize: 11, textTransform: 'capitalize' },
    cardDesc: { color: C.textSec, fontSize: 12, lineHeight: 18 },
    planBadgesRow: { marginTop: 10, flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    planBadge: {
      borderRadius: 999,
      borderWidth: 1,
      paddingHorizontal: 7,
      paddingVertical: 4,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 4,
    },
    planBadgeUnlocked: { borderColor: `${C.success}66`, backgroundColor: `${C.success}14` },
    planBadgeLocked: { borderColor: `${C.warning}66`, backgroundColor: `${C.warning}14` },
    planBadgeActive: { shadowColor: C.primary, shadowOpacity: 0.25, shadowRadius: 6, shadowOffset: { width: 0, height: 1 } },
    planBadgeText: { fontSize: 9, fontWeight: '800' },
    planBadgeTextUnlocked: { color: C.successText },
    planBadgeTextLocked: { color: C.warningText },
    emptyState: { alignItems: 'center', paddingVertical: 42 },
    emptyTitle: { marginTop: 10, color: C.text, fontSize: 15, fontWeight: '700' },
    emptySubtitle: { marginTop: 4, color: C.textMuted, fontSize: 12 },
  });
