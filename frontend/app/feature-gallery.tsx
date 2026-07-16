import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, ScrollView, StatusBar,
  StyleSheet, Platform, Animated, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useFeatures } from '@/src/context/FeaturesContext';
import { useTheme } from '@/src/context/ThemeContext';
import { useAuth } from '@/src/context/AuthContext';
import { useTranslation } from '@/src/hooks/useTranslation';
import { GalleryCard } from '@/src/components/gallery/GalleryCard';
import { GallerySkeleton} from '@/src/components/SkeletonLoaders';
import AppShell from '@/src/components/AppShell';
import { ProtectedRouteGate } from '@/src/components/auth/ProtectedRouteGate';

type FeatureItem = {
  id?: string;
  feature_id?: string;
  title: string;
  description: string;
  icon: string;
  route: string;
  category: string;
  color: string;
  isNew?: boolean;
};

export default function FeatureGalleryScreen() {
  const { colors, darkMode } = useTheme();
  const { user, loading: authLoading } = useAuth();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const normalizeFeatureDescription = useCallback((feature: FeatureItem) => {
    const raw = String(feature?.description || '').trim();
    if (!raw || ['description', 'subtitle'].includes(raw.toLowerCase())) {
      return tx('features.card.descriptionFallback', 'Open this feature and continue your workflow with AI-guided support.');
    }
    return raw;
  }, [tx]);
  const router = useRouter();
  const { width } = useWindowDimensions();
  const isDesktop = width >= 1024;
  const isTablet = width >= 600;
  const accentColor = darkMode ? colors.accent : colors.success;

  const { features: dynamicFeatures, categories: dynamicCategories, loading, lastUpdated } = useFeatures();
  const allFeatures = dynamicFeatures;
  const allCategories = dynamicCategories.length > 0
    ? dynamicCategories
    : [{ id: 'all', label: tx('features.category.all', 'All') }, ...Array.from(new Set(allFeatures.map((f) => f.category))).map((cat) => ({ id: cat, label: tx(`features.category.${String(cat)}`, String(cat).replace(/-/g, ' ').replace(/\b\w/g, (s) => s.toUpperCase())) }))];

  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');
  const CAREER_OPS_FEATURE_IDS = useMemo(
    () => new Set(['jobs-portal', 'referrals', 'id-checker', 'book-meeting', 'integrations', 'library']),
    [],
  );
  const effectivePlan = String(user?.subscription_plan || 'free').toLowerCase();
  const planScopeLabel = effectivePlan === 'premium'
    ? tx('featureGallery.planScope.premium', 'Full unlimited access')
    : effectivePlan === 'basic'
      ? tx('featureGallery.planScope.basic', 'Almost unlimited access')
      : tx('featureGallery.planScope.free', 'Limited access');
  const enabledFeaturesCount = useMemo(
    () => allFeatures.filter((f: any) => f?.enabled !== false).length,
    [allFeatures],
  );
  const operationsReadinessPct = useMemo(() => {
    if (!allFeatures.length) return 0;
    return Math.round((enabledFeaturesCount / allFeatures.length) * 100);
  }, [allFeatures.length, enabledFeaturesCount]);
  const syncTimestampLabel = useMemo(() => {
    if (!lastUpdated) return tx('featureGallery.sync.syncing', 'syncing');
    const t = Date.parse(String(lastUpdated));
    if (!Number.isFinite(t)) return 'syncing';
    const delta = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (delta < 60) return `${delta}s ago`;
    const mins = Math.floor(delta / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    return `${hours}h ago`;
  }, [lastUpdated, tx]);

  const fadeA = useRef(new Animated.Value(0)).current;
  const slideA = useRef(new Animated.Value(24)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeA, { toValue: 1, duration: 700, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideA, { toValue: 0, duration: 700, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const spotlightFeatures = useMemo(
    () => allFeatures.filter((f) => CAREER_OPS_FEATURE_IDS.has(String(f.feature_id || ''))),
    [CAREER_OPS_FEATURE_IDS, allFeatures],
  );

  const showSpotlight = category === 'all' && !search.trim() && spotlightFeatures.length > 0;

  const filtered = useMemo(() => {
    let list = allFeatures;
    if (category !== 'all') list = list.filter(f => f.category === category);
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(f => f.title.toLowerCase().includes(q) || normalizeFeatureDescription(f).toLowerCase().includes(q));
    }
    if (showSpotlight) {
      list = list.filter((f) => !CAREER_OPS_FEATURE_IDS.has(String(f.feature_id || '')));
    }
    return list;
  }, [category, search, allFeatures, showSpotlight, CAREER_OPS_FEATURE_IDS, normalizeFeatureDescription]);

  const handleFeaturePress = useCallback((feature: FeatureItem) => {
    router.push(feature.route as any);
  }, [router]);

  const blur = Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {};

  // Dark mode: readable glass surfaces — opaque enough for text clarity, subtle glass for premium feel.
  // Uses V2 theme tokens (colors.card / colors.surface) so the palette flips with the theme.
  const darkKpiCardStyle = (kpiColor: string) => darkMode ? {
    backgroundColor: (globalThis as any).__alphaColor(colors.card, 'B6'),
    borderColor: (globalThis as any).__alphaColor(kpiColor, '30'),
    ...(Platform.OS === 'web' ? { boxShadow: `0 4px 20px ${kpiColor}12`, backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}),
  } : {};
  const darkSearchStyle = darkMode ? {
    backgroundColor: (globalThis as any).__alphaColor(colors.card, 'B6'),
    borderColor: colors.border,
    ...(Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}),
  } : {};
  const darkPillStyle = darkMode ? {
    backgroundColor: (globalThis as any).__alphaColor(colors.card, 'AE'),
    borderColor: colors.border,
  } : {};
  const shellSurface = Platform.OS === 'web'
    ? (globalThis as any).__alphaColor(colors.card, darkMode ? '9E' : 'D8')
    : colors.card;

  // Card width based on screen
  const cardWidth = isDesktop ? '23.5%' : isTablet ? '48%' : '100%';
  const spotlightCardWidth = isDesktop ? 320 : isTablet ? 300 : Math.max(260, width - 76);
  const fmtK = (n: number) => n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'K' : n.toString();
  const galleryHeaderSubtitle = tx('featureGallery.header.subtitle', 'Enterprise-grade AI capabilities orchestrated for operations, compliance, and growth');

  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={Boolean(user?.user_id)} returnTo="/feature-gallery">
      <AppShell>
        <View style={[s.root, { backgroundColor: 'transparent' }]} data-testid="feature-gallery-screen" testID="feature-gallery-screen">
          <StatusBar barStyle={darkMode ? 'light-content' : 'dark-content'} />
          <ScrollView style={s.scroll} contentContainerStyle={s.scrollContent} showsVerticalScrollIndicator={false}>
        <Animated.View style={{ opacity: fadeA, transform: [{ translateY: slideA }] }}>

          {/* Header */}
          <View style={s.headerSection}>
            <TouchableOpacity onPress={() => router.back()} style={[s.backBtn, { backgroundColor: darkMode ? 'rgba(10,18,36,0.88)' : colors.card, borderColor: darkMode ? 'rgba(51,65,85,0.5)' : colors.border }, darkMode && Platform.OS === 'web' ? { backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)' } as any : {}]} data-testid="gallery-back-btn" testID="gallery-back-btn">
              <Ionicons name="arrow-back" size={18} color={darkMode ? colors.textSec : colors.textSec} />
            </TouchableOpacity>
            <View style={s.headerTextWrap}>
              <Text style={[s.headerTitle, { color: colors.text }]} data-testid="gallery-title" testID="gallery-title">{tx('featureGallery.header.title', 'Feature Functionality Hub')}</Text>
              <Text style={[s.headerSub, { color: darkMode ? colors.textMuted : colors.textMuted }]} data-testid="gallery-header-subtitle" testID="gallery-header-subtitle">
                {galleryHeaderSubtitle}
              </Text>
            </View>
          </View>

          {/* Plan Access Banner */}
          <View style={[s.kpiRow, isDesktop && { gap: 16 }]} data-testid="gallery-plan-access-row" testID="gallery-plan-access-row">
            <View style={[s.kpiCard, { backgroundColor: shellSurface, borderColor: colors.border }, darkKpiCardStyle(accentColor), blur]} data-testid="gallery-plan-access-card" testID="gallery-plan-access-card">
              <View style={[s.kpiIconBox, { backgroundColor: accentColor + (darkMode ? '20' : '12') }]}> 
                <Ionicons name="shield-checkmark" size={16} color={accentColor} />
              </View>
              <Text style={[s.kpiValue, { color: colors.text }]} data-testid="gallery-plan-value" testID="gallery-plan-value">{tx(`subscriptionPlans.plan.${effectivePlan}.name`, String(effectivePlan).toUpperCase())}</Text>
              <Text style={[s.kpiLabel, { color: darkMode ? colors.textMuted : colors.textMuted }]} data-testid="gallery-plan-scope" testID="gallery-plan-scope">{planScopeLabel}</Text>
            </View>
            <View style={[s.kpiCard, { backgroundColor: shellSurface, borderColor: colors.border }, darkKpiCardStyle(colors.indigoText), blur]} data-testid="gallery-features-total-card" testID="gallery-features-total-card">
              <View style={[s.kpiIconBox, { backgroundColor: colors.indigoText + (darkMode ? '20' : '12') }]}> 
                <Ionicons name="apps" size={16} color={colors.indigoText} />
              </View>
              <Text style={[s.kpiValue, { color: colors.text }]}>{fmtK(allFeatures.length)}</Text>
              <Text style={[s.kpiLabel, { color: darkMode ? colors.textMuted : colors.textMuted }]}>{tx('featureGallery.kpi.liveFeatures', 'Live Features')}</Text>
            </View>
            <View style={[s.kpiCard, { backgroundColor: shellSurface, borderColor: colors.border }, darkKpiCardStyle(colors.successText), blur]} data-testid="gallery-ops-readiness-card" testID="gallery-ops-readiness-card">
              <View style={[s.kpiIconBox, { backgroundColor: colors.successText + (darkMode ? '20' : '12') }]}> 
                <Ionicons name="pulse" size={16} color={colors.successText} />
              </View>
              <Text style={[s.kpiValue, { color: colors.text }]} data-testid="gallery-ops-readiness-value" testID="gallery-ops-readiness-value">
                {operationsReadinessPct}%
              </Text>
              <Text style={[s.kpiLabel, { color: darkMode ? colors.textMuted : colors.textMuted }]} data-testid="gallery-ops-readiness-label" testID="gallery-ops-readiness-label">
                {tx('featureGallery.kpi.opsReadiness', 'Ops Readiness')}
              </Text>
              <Text style={[s.kpiMeta, { color: colors.textMuted }]} data-testid="gallery-ops-readiness-meta" testID="gallery-ops-readiness-meta">
                {enabledFeaturesCount}/{allFeatures.length} {tx('featureGallery.kpi.active', 'active')} • {tx('featureGallery.kpi.updated', 'Updated')} {syncTimestampLabel}
              </Text>
            </View>
          </View>

          {/* Search + Filter */}
          <View style={s.filterRow}>
            <View style={[s.searchBox, { backgroundColor: shellSurface, borderColor: colors.border }, darkSearchStyle, blur]}>
              <Ionicons name="search" size={16} color={darkMode ? colors.textMuted : colors.textMuted} />
              <TextInput
                style={[s.searchInput, { color: colors.text }]}
                placeholder={tx('features.search.placeholder.fallback', 'Search features')}
                placeholderTextColor={darkMode ? colors.textMuted : colors.textMuted}
                value={search}
                onChangeText={setSearch}
                data-testid="gallery-search-input" testID="gallery-search-input"
              />
              {search.length > 0 && (
                <TouchableOpacity onPress={() => setSearch('')} data-testid="gallery-search-clear" testID="gallery-search-clear">
                  <Ionicons name="close-circle" size={16} color={colors.textMuted} />
                </TouchableOpacity>
              )}
            </View>
          </View>

          {/* Category Pills */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.catScroll} contentContainerStyle={s.catContent}>
            {allCategories.map(c => {
              const count = c.id === 'all' ? allFeatures.length : allFeatures.filter(f => f.category === c.id).length;
              const isActive = category === c.id;
              return (
                <TouchableOpacity
                  key={c.id}
                  style={[
                    s.catPill,
                    { borderColor: colors.border },
                    !isActive && darkPillStyle,
                    isActive && { backgroundColor: accentColor, borderColor: accentColor },
                  ]}
                  onPress={() => setCategory(c.id)}
                  data-testid={`gallery-cat-${c.id}`} testID={`gallery-cat-${c.id}`}
                >
                  <Text style={[s.catText, { color: darkMode ? colors.textSec : colors.textSec }, isActive && { color: colors.primaryText || colors.buttonText || colors.text }]}>
                    {c.label} ({count})
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* Results count */}
          <View style={s.resultsRow}>
            <Text style={[s.resultsText, { color: colors.textMuted }]} data-testid="gallery-results-count" testID="gallery-results-count">
              {filtered.length} {tx('featureGallery.results.available', 'capabilities currently available in this view')}
            </Text>
          </View>

          {showSpotlight ? (
            <View style={s.spotlightSection} data-testid="gallery-career-ops-spotlight" testID="gallery-career-ops-spotlight">
              <View style={s.spotlightHeader}>
                <Text style={[s.spotlightTitle, { color: colors.text }]} data-testid="gallery-career-ops-title" testID="gallery-career-ops-title">
                  {tx('featureGallery.spotlight.title', 'Career & Operations Spotlight')}
                </Text>
                <Text style={[s.spotlightSub, { color: colors.textMuted }]} data-testid="gallery-career-ops-subtitle" testID="gallery-career-ops-subtitle">
                  {tx('featureGallery.spotlight.subtitle', 'High-impact workflows for hiring, referrals, compliance, and operations.')}
                </Text>
              </View>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={s.spotlightScrollContent}
                data-testid="gallery-career-ops-scroll"
                testID="gallery-career-ops-scroll"
              >
                {spotlightFeatures.map((feature) => (
                  <View
                    key={`spotlight-${feature.id || feature.feature_id}`}
                    style={s.spotlightCardWrap}
                    data-testid={`gallery-spotlight-card-${feature.feature_id || feature.id}`}
                    testID={`gallery-spotlight-card-${feature.feature_id || feature.id}`}
                  >
                    <GalleryCard
                      feature={feature}
                      metrics={null}
                      onPress={() => handleFeaturePress(feature)}
                      colors={colors}
                      accentColor={accentColor}
                      cardWidth={spotlightCardWidth}
                      darkMode={darkMode}
                    />
                  </View>
                ))}
              </ScrollView>
            </View>
          ) : null}

          {/* Feature Grid */}
          {loading ? (
            <GallerySkeleton />
          ) : (
            <View style={[s.grid, isDesktop && s.gridDesktop, isTablet && !isDesktop && s.gridTablet]} data-testid="gallery-grid" testID="gallery-grid">
              {filtered.map(feature => (
                <GalleryCard
                  key={feature.id || feature.feature_id}
                  feature={feature}
                  metrics={null}
                  onPress={() => handleFeaturePress(feature)}
                  colors={colors}
                  accentColor={accentColor}
                  cardWidth={cardWidth}
                  darkMode={darkMode}
                />
              ))}
            </View>
          )}

          {filtered.length === 0 && !loading && (
            <View style={s.emptyWrap} data-testid="gallery-empty" testID="gallery-empty">
              <Ionicons name="search" size={40} color={colors.textMuted} />
              <Text style={[s.emptyTitle, { color: colors.text }]}>{tx('features.empty.title', 'No features found')}</Text>
              <Text style={[s.emptyDesc, { color: colors.textMuted }]}>{tx('featureGallery.empty.body', 'Try adjusting your search or filter criteria')}</Text>
              <TouchableOpacity style={[s.resetBtn, { borderColor: accentColor }]} onPress={() => { setSearch(''); setCategory('all'); }} data-testid="gallery-reset-filters" testID="gallery-reset-filters">
                <Text style={[s.resetText, { color: accentColor }]}>{tx('featureGallery.empty.reset', 'Reset Filters')}</Text>
              </TouchableOpacity>
            </View>
          )}

        </Animated.View>
          </ScrollView>

        </View>
      </AppShell>
    </ProtectedRouteGate>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, position: 'relative' },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: 40 },

  // Header
  headerSection: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: 20, paddingTop: 16, paddingBottom: 8 },
  backBtn: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  headerTextWrap: { flex: 1 },
  headerTitle: { fontSize: 24, fontWeight: '900', letterSpacing: -0.5 },
  headerSub: { fontSize: 13, marginTop: 2 },

  // KPI
  kpiRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingVertical: 16, flexWrap: 'wrap' },
  kpiCard: { flex: 1, minWidth: 120, borderRadius: 16, padding: 16, borderWidth: 1, alignItems: 'center', gap: 6 },
  kpiIconBox: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  kpiValue: { fontSize: 22, fontWeight: '800', letterSpacing: -0.5 },
  kpiLabel: { fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 },
  kpiMeta: { fontSize: 10, fontWeight: '600', textAlign: 'center' },

  // Search
  filterRow: { paddingHorizontal: 20, marginBottom: 12 },
  searchBox: { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 14, borderWidth: 1, paddingHorizontal: 16, paddingVertical: 12 },
  searchInput: { flex: 1, fontSize: 14, fontWeight: '500', padding: 0 },

  // Categories
  catScroll: { marginBottom: 12 },
  catContent: { paddingHorizontal: 20, gap: 8 },
  catPill: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(148,163,184,0.1)' },
  catText: { fontSize: 13, fontWeight: '600' },

  // Results
  resultsRow: { paddingHorizontal: 20, marginBottom: 12 },
  resultsText: { fontSize: 12, fontWeight: '600' },

  // Spotlight
  spotlightSection: { paddingHorizontal: 20, marginBottom: 16, gap: 10 },
  spotlightHeader: { gap: 4 },
  spotlightTitle: { fontSize: 18, fontWeight: '800', letterSpacing: -0.3 },
  spotlightSub: { fontSize: 12, fontWeight: '500' },
  spotlightScrollContent: { gap: 12, paddingRight: 10 },
  spotlightCardWrap: { width: 'auto' },

  // Grid
  grid: { paddingHorizontal: 20, gap: 14 },
  gridDesktop: { flexDirection: 'row', flexWrap: 'wrap', gap: 14 },
  gridTablet: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },

  // Loading
  loadingWrap: { padding: 60, alignItems: 'center', gap: 12 },
  loadingText: { fontSize: 14 },

  // Empty
  emptyWrap: { padding: 60, alignItems: 'center', gap: 10 },
  emptyTitle: { fontSize: 18, fontWeight: '700' },
  emptyDesc: { fontSize: 14, textAlign: 'center' },
  resetBtn: { marginTop: 12, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 10, borderWidth: 1 },
  resetText: { fontSize: 14, fontWeight: '600' },
});
