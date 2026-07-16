import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, FlatList, RefreshControl, Platform, TouchableOpacity, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router, Redirect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/context/AuthContext';
import { useTheme } from '../../src/context/ThemeContext';
import { useLiveMetrics } from '../../src/hooks/useLiveMetrics';
import { useLiveQuery } from '../../src/hooks/useLiveQuery';
import { useGlobalPlatformState } from '../../src/hooks/useGlobalPlatformState';
import { buildCanonicalWelcomeTestimonials } from '../../src/content/welcomeTrustContent';
import { useFeatures } from '../../src/context/FeaturesContext';
import api from '../../src/services/api';
import AppShell from '../../src/components/AppShell';
import { HomeSkeleton, FadeSlideIn } from '../../src/components/SkeletonLoaders';
import { ProtectedRouteGate } from '../../src/components/auth/ProtectedRouteGate';
import HomeHero from '../../src/components/home/HomeHero';
import HomeDashboardCharts from '../../src/components/home/HomeDashboardCharts';
import HomeActivityPulse from '../../src/components/home/HomeActivityPulse';
import HomeJobHuntPulse from '../../src/components/home/HomeJobHuntPulse';
import HomeArcadeChallenge from '../../src/components/home/HomeArcadeChallenge';
import HomeFeatureHighlights from '../../src/components/home/HomeFeatureHighlights';
import HomeSocialProof from '../../src/components/home/HomeSocialProof';
import HomeCTA from '../../src/components/home/HomeCTA';
import HomeOnboardingTour from '../../src/components/home/HomeOnboardingTour';
import HomeChecklist from '../../src/components/home/HomeChecklist';
import HomeTrophyCase from '../../src/components/home/HomeTrophyCase';
import HomeContinueToast from '../../src/components/home/HomeContinueToast';
import OnboardingWizard from '../../src/components/OnboardingWizard';
import GpsLabelBlocker from '../../src/components/GpsLabelBlocker';
import HomeNovaAssistantWidget from '../../src/components/home/HomeNovaAssistantWidget';
import HomeEnterpriseCommandDeck from '../../src/components/home/HomeEnterpriseCommandDeck';
import HomeExecutiveOverviewBand from '../../src/components/home/HomeExecutiveOverviewBand';
import { GpsDataStatusCard } from '../../src/components/GpsDataStatusCard';
import { useTranslation } from '../../src/hooks/useTranslation';
import EnterpriseDisclaimerToken from '../../src/components/tokens/EnterpriseDisclaimerToken';
import { NOVA_INTRO_FALLBACK } from '../../src/constants/novaPersona';
import { NovaIdentityCallout } from '../../src/components/common/NovaIdentityBadge';
import { SectionProgressRail } from '../../src/components/progress/SectionProgressRail';
import { handleAppRecoverableError } from '../../src/utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../../src/utils/adminAccess';

const GLOBAL_CSS = `
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
html, body { scroll-behavior: smooth; }
`;

type HomeSectionId = 'hero' | 'command' | 'checklist' | 'charts' | 'features' | 'trophies' | 'social' | 'cta';

type HomeSectionItem = {
  id: HomeSectionId;
  estimatedHeight: number;
};

const HOME_SECTION_VIRTUAL_ITEMS: HomeSectionItem[] = [
  { id: 'hero', estimatedHeight: 760 },
  { id: 'command', estimatedHeight: 720 },
  { id: 'checklist', estimatedHeight: 520 },
  { id: 'charts', estimatedHeight: 620 },
  { id: 'features', estimatedHeight: 500 },
  { id: 'trophies', estimatedHeight: 520 },
  { id: 'social', estimatedHeight: 420 },
  { id: 'cta', estimatedHeight: 430 },
];

export default function HomeScreen() {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  t('i18n.route.(tabs).index.probe');
  const { user, isAuthenticated, loading: authLoading } = useAuth();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const [homeContentWidth, setHomeContentWidth] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const {
    counts: gpsCounts,
    state: gpsState,
    strictLabel,
    getMissingLabels,
    loading: gpsLoading,
    error: gpsError,
    refetch: gpsRefetch,
    diagnostics: gpsDiagnostics,
  } = useGlobalPlatformState();
  const homeTrustCompanies = useMemo(
    () => Array.from(new Set(
      buildCanonicalWelcomeTestimonials((gpsState?.messaging as any)?.welcome_testimonials, 10)
        .map((item) => String(item.company || '').trim())
        .filter(Boolean)
    )).slice(0, 8),
    [gpsState?.messaging]
  );
  const { totalCount: liveFeatureRegistryCount } = useFeatures();
  const { data: liveMetricsData, vanity: liveVanity, loading, error: statsError, refetch } = useLiveMetrics(3000);
  const {
    data: commandDeckData,
    loading: commandDeckLoading,
    refetch: refetchCommandDeck,
  } = useLiveQuery('/home/enterprise-command-center', { entity: 'home_command_center', pollInterval: 30000 });

  const liveStats = useMemo(() => {
    if (!liveVanity) return null;
    return {
      active_users: liveVanity.active_users,
      ai_sessions_today: liveVanity.ai_sessions_today,
      performance_boost: liveVanity.performance_boost,
      global_coaches: liveVanity.global_coaches,
      total_users: liveMetricsData?.kpis?.total_users || liveVanity.active_users || 0,
      ai_status: 'online',
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    liveMetricsData?.kpis?.total_users,
    liveVanity?.active_users,
    liveVanity?.ai_sessions_today,
    liveVanity?.performance_boost,
    liveVanity?.global_coaches,
  ]);

  const stats = useMemo(() => (liveStats || {
    active_users: 0,
    ai_sessions_today: 0,
    performance_boost: 0,
    global_coaches: 0,
    total_users: 0,
    ai_status: 'online',
  }), [liveStats]);
  const userName = user?.name || 'User';
  const resolvedFeatureCount = gpsCounts.features > 0 ? gpsCounts.features : Math.max(0, liveFeatureRegistryCount || 0);
  const error = !!statsError;
  const viewerIsAdmin = hasAdminConsoleVisibility(user as any);
  const requiredHomeLabelKeys = [
    'home.stale.title',
    'home.stale.subtitle',
    'home.stale.retry',
    'home.tour.title',
    'home.nova.fab.template',
    'home.nova.panel.title',
    'home.nova.panel.subtitle',
    'home.nova.input.placeholder',
    'home.nova.send',
    'home.nova.close',
    'home.nova.welcome',
    'home.nova.error.unauthorized',
    'home.nova.error.generic',
    'home.nova.context.summary',
    'home.nova.launcher.aria',
    'home.nova.search.prefill',
    'home.nova.context.title',
    'home.nova.loading',
    'home.nova.search.accessibility',
    'home.nova.close.accessibility',
    'home.nova.send.accessibility',
  ];
  const missingHomeLabels = getMissingLabels(requiredHomeLabelKeys);
  const staleDashboardTitle = strictLabel('home.stale.title') || '';
  const staleDashboardSubtitle = strictLabel('home.stale.subtitle') || '';
  const staleDashboardRetry = strictLabel('home.stale.retry') || '';
  const takeTourTitle = strictLabel('home.tour.title') || '';
  const homeNovaLabels = {
    fabTemplate: strictLabel('home.nova.fab.template') || tx('home.nova.fab.template', 'Nova — {{status}}'),
    panelTitle: strictLabel('home.nova.panel.title') || tx('home.nova.panel.title', 'Nova'),
    panelSubtitle: strictLabel('home.nova.panel.subtitle') || tx('home.nova.panel.subtitle', 'AI Assistant'),
    inputPlaceholder: strictLabel('home.nova.input.placeholder') || tx('home.nova.input.placeholder', 'Ask Nova anything...'),
    sendLabel: strictLabel('home.nova.send') || tx('home.nova.send', 'Send'),
    closeLabel: strictLabel('home.nova.close') || tx('home.nova.close', 'Close'),
    welcomeMessage: strictLabel('home.nova.welcome') || tx('home.nova.welcome', 'Hi! I’m Nova, your AI assistant. How can I help you today?'),
    unauthorizedError: strictLabel('home.nova.error.unauthorized') || tx('home.nova.error.unauthorized', 'Please sign in again to continue chatting with Nova.'),
    genericError: strictLabel('home.nova.error.generic') || tx('home.nova.error.generic', 'I’m having trouble connecting right now. Please try again.'),
    contextSummaryTemplate: strictLabel('home.nova.context.summary') || tx('home.nova.context.summary', 'Workspace coverage: {{features}} live features · {{plans}} active plans.'),
    launcherAriaLabel: strictLabel('home.nova.launcher.aria') || tx('home.nova.launcher.aria', 'Open Nova assistant'),
    searchPrefill: strictLabel('home.nova.search.prefill') || tx('home.nova.search.prefill', 'Summarize my next best action'),
    contextTitle: strictLabel('home.nova.context.title') || tx('home.nova.context.title', 'Command context'),
    loadingLabel: strictLabel('home.nova.loading') || tx('home.nova.loading', 'Nova is thinking...'),
    searchAccessibilityLabel: strictLabel('home.nova.search.accessibility') || tx('home.nova.search.accessibility', 'Search Nova prompts'),
    closeAccessibilityLabel: strictLabel('home.nova.close.accessibility') || tx('home.nova.close.accessibility', 'Close Nova panel'),
    sendAccessibilityLabel: strictLabel('home.nova.send.accessibility') || tx('home.nova.send.accessibility', 'Send Nova message'),
    compactLatestReply: strictLabel('home.nova.compact.latest-reply') || tx('home.nova.compact.latest-reply', 'Latest reply'),
    compactExpandCta: strictLabel('home.nova.compact.expand') || tx('home.nova.compact.expand', 'Open full conversation'),
    compactCollapse: strictLabel('home.nova.compact.collapse') || tx('home.nova.compact.collapse', 'Compact view'),
    compactEmpty: strictLabel('home.nova.compact.empty') || tx('home.nova.compact.empty', 'No conversation yet - pick a quick prompt to get started.'),
    enterpriseIntro: strictLabel('home.nova.enterpriseIntro') || "I'm Nova, I will be your AI assistant for any questions regarding this platform.",
  };
  const homeNovaInlineIntro = (homeNovaLabels.enterpriseIntro || '').trim() || NOVA_INTRO_FALLBACK;
  const [tourVisible, setTourVisible] = useState(false);
  const [tourChecked, setTourChecked] = useState(false);
  const [wizardVisible, setWizardVisible] = useState(false);
  const [wizardChecked, setWizardChecked] = useState(false);
  const [homeRecoverableError, setHomeRecoverableError] = useState('');
  const [secondaryModulesReady, setSecondaryModulesReady] = useState(false);
  const [activeSection, setActiveSection] = useState('hero');
  const sectionOffsetsRef = useRef<Record<string, number>>({});
  const activeSectionRef = useRef('hero');
  const scrollRef = useRef<FlatList<HomeSectionItem> | null>(null);
  const fallbackContentWidth = width >= 1024 ? Math.max(0, width - (width >= 1600 ? 272 : 256)) : width;
  const responsiveWidth = homeContentWidth > 0 ? homeContentWidth : fallbackContentWidth;
  const showProgressRail = responsiveWidth >= 1450;
  const homeSectionItems = useMemo(() => ([
    { id: 'hero', label: tx('home.section.hero', 'Briefing'), icon: 'planet-outline' },
    { id: 'command', label: tx('home.section.command', 'Command deck'), icon: 'flash-outline' },
    { id: 'checklist', label: tx('home.section.checklist', 'Momentum'), icon: 'checkbox-outline' },
    { id: 'charts', label: tx('home.section.charts', 'Signals'), icon: 'analytics-outline' },
    { id: 'features', label: tx('home.section.features', 'Feature stack'), icon: 'apps-outline' },
    { id: 'trophies', label: tx('home.section.trophies', 'Wins'), icon: 'trophy-outline' },
    { id: 'social', label: tx('home.section.social', 'Proof'), icon: 'people-outline' },
    { id: 'cta', label: tx('home.section.cta', 'Next step'), icon: 'rocket-outline' },
  ]), [tx]);
  const homeNovaQuickPrompts = useMemo(() => ([
    tx('home.nova.quickPrompt.summary', 'Summarize my top priorities today'),
    tx('home.nova.quickPrompt.momentum', 'Where am I losing momentum right now?'),
    tx('home.nova.quickPrompt.action', 'Give me the fastest high-value next action'),
  ]), [tx]);
  const homeVirtualItems = useMemo(() => HOME_SECTION_VIRTUAL_ITEMS, []);
  const homeSectionIndexById = useMemo(() => {
    const map: Record<string, number> = {};
    homeVirtualItems.forEach((item, index) => {
      map[item.id] = index;
    });
    return map;
  }, [homeVirtualItems]);
  const homeSectionOffsetByEstimate = useMemo(() => {
    const map: Record<string, number> = {};
    let cursor = 0;
    homeVirtualItems.forEach((item, index) => {
      map[item.id] = cursor;
      const isLast = index === homeVirtualItems.length - 1;
      cursor += item.estimatedHeight + (isLast ? 0 : 24);
    });
    return map;
  }, [homeVirtualItems]);

  const retryHomeAuxChecks = useCallback(() => {
    setHomeRecoverableError('');
    setTourChecked(false);
    setWizardChecked(false);
  }, []);

  useEffect(() => {
    if (Platform.OS === 'web') {
      const id = 'home-global-css';
      if (!document.getElementById(id)) {
        const s = document.createElement('style');
        s.id = id;
        s.textContent = GLOBAL_CSS;
        document.head.appendChild(s);
      }
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setSecondaryModulesReady(false);
      return;
    }

    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let idleHandle: any = null;
    const ready = () => setSecondaryModulesReady(true);
    if (Platform.OS === 'web' && typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      idleHandle = (window as any).requestIdleCallback(ready, { timeout: 1200 });
    } else {
      timeoutId = setTimeout(ready, 700);
    }

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (idleHandle && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        (window as any).cancelIdleCallback(idleHandle);
      }
    };
  }, [isAuthenticated]);

  // Check tour status once data loads
  useEffect(() => {
    if (Platform.OS !== 'web' || loading || tourChecked || !secondaryModulesReady) return;
    const checkTour = async () => {
      try {
        const res = await api.get('/home/tour-status');
        setTourChecked(true);
        setHomeRecoverableError('');
        if (!res.data.completed) {
          setTourVisible(false);
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'home.index.tour-status',
          error,
          message: tx('home.recoverable.tourStatusFailed', 'Could not check tour status.'),
          setError: setHomeRecoverableError,
          onRetry: () => { void checkTour(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setTourChecked(true);
      }
    };
    checkTour();
  }, [loading, secondaryModulesReady, tourChecked, tx]);

  // Check onboarding wizard status — show for users who haven't completed it
  useEffect(() => {
    if (loading || wizardChecked || !secondaryModulesReady) return;
    const checkWizard = async () => {
      try {
        // Only show wizard after TOS is accepted (TOS wall takes priority)
        const tosRes = await api.get('/tos/acceptance-status');
        if (tosRes.data && !tosRes.data.accepted) {
          setWizardChecked(true);
          return; // TOS wall is blocking — don't show wizard yet
        }
        const res = await api.get('/onboarding-wizard/status');
        setWizardChecked(true);
        setHomeRecoverableError('');
        if (!res.data.completed) {
          setTimeout(() => setWizardVisible(true), 800);
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'home.index.wizard-status',
          error,
          message: tx('home.recoverable.wizardStatusFailed', 'Could not check onboarding status.'),
          setError: setHomeRecoverableError,
          onRetry: () => { void checkWizard(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
        setWizardChecked(true);
      }
    };
    checkWizard();
  }, [loading, secondaryModulesReady, wizardChecked, tx]);

  const onRefresh = () => {
    setRefreshing(true);
    Promise.allSettled([refetch(), refetchCommandDeck(), gpsRefetch()]).finally(() => setRefreshing(false));
  };

  const setSectionOffset = (key: string, y: number) => {
    sectionOffsetsRef.current[key] = y;
  };

  const scrollToSection = (key: string) => {
    const index = homeSectionIndexById[key];
    if (typeof index === 'number') {
      scrollRef.current?.scrollToIndex?.({
        index,
        viewOffset: 70,
        animated: true,
      });
      return;
    }

    const y = sectionOffsetsRef.current[key];
    if (typeof y !== 'number' || !Number.isFinite(y)) return;
    scrollRef.current?.scrollToOffset?.({ offset: Math.max(0, y - 70), animated: true });
  };

  const onHomeScroll = (event: any) => {
    const y = event?.nativeEvent?.contentOffset?.y || 0;
    const ordered = Object.entries(sectionOffsetsRef.current)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
      .sort((a, b) => a[1] - b[1]);

    let next = 'hero';
    for (const [key, offsetY] of ordered) {
      if (y + 140 >= offsetY) {
        next = key;
      }
    }

    if (next !== activeSectionRef.current) {
      activeSectionRef.current = next;
      setActiveSection(next);
    }
  };

  const getHomeSectionLayout = useCallback((_: ArrayLike<HomeSectionItem> | null | undefined, index: number) => {
    const item = homeVirtualItems[index];
    const offset = item ? homeSectionOffsetByEstimate[item.id] : index * 560;
    const length = item?.estimatedHeight || 560;
    return { index, length, offset };
  }, [homeSectionOffsetByEstimate, homeVirtualItems]);

  const onHomeScrollToIndexFailed = useCallback((info: { index: number; averageItemLength: number }) => {
    const item = homeVirtualItems[info.index];
    const measuredOffset = item ? sectionOffsetsRef.current[item.id] : undefined;
    const estimateOffset = item ? homeSectionOffsetByEstimate[item.id] : info.index * info.averageItemLength;
    const fallbackOffset = typeof measuredOffset === 'number' ? measuredOffset : estimateOffset;
    scrollRef.current?.scrollToOffset?.({
      offset: Math.max(0, fallbackOffset - 70),
      animated: true,
    });
  }, [homeSectionOffsetByEstimate, homeVirtualItems]);

  const renderHomeSection = useCallback(({ item }: { item: HomeSectionItem }) => {
    const sectionSpacing = item.id === 'hero' ? 0 : 24;

    if (item.id === 'hero') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('hero', e.nativeEvent.layout.y)} data-testid="home-section-hero" testID="home-section-hero">
          <HomeHero
            responsiveWidth={responsiveWidth}
            stats={stats}
            userName={userName}
            onStartJourney={() => router.push('/feature-gallery')}
            onExploreTools={() => router.push('/feature-gallery')}
          />
        </View>
      );
    }

    if (item.id === 'command') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('command', e.nativeEvent.layout.y)} data-testid="home-section-command" testID="home-section-command">
          <HomeEnterpriseCommandDeck
            responsiveWidth={responsiveWidth}
            payload={commandDeckData}
            loading={commandDeckLoading}
            onNavigate={(route) => router.push((route || '/dashboard') as any)}
          />
          <View style={{ marginHorizontal: 20, marginTop: 10 }}>
            <NovaIdentityCallout
              prefix="home-inline-nova"
              kicker="Meet Nova"
              introText={homeNovaInlineIntro}
              borderColor={colors.warningText}
              backgroundColor={`${colors.warningText}14`}
              kickerColor={colors.warningText}
              textColor={colors.text}
              avatarRingColor={colors.error}
              avatarSurfaceColor={colors.card}
              avatarSize={44}
              avatarAnimationPreset="subtle"
              introTestId="home-inline-nova-intro-text"
            />
          </View>
        </View>
      );
    }

    if (item.id === 'checklist') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('checklist', e.nativeEvent.layout.y)} data-testid="home-section-checklist" testID="home-section-checklist">
          {secondaryModulesReady ? <HomeChecklist responsiveWidth={responsiveWidth} /> : null}
        </View>
      );
    }

    if (item.id === 'charts') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('charts', e.nativeEvent.layout.y)} data-testid="home-section-charts" testID="home-section-charts">
          {secondaryModulesReady ? (
            <>
              <HomeDashboardCharts responsiveWidth={responsiveWidth} />
              <HomeActivityPulse responsiveWidth={responsiveWidth} />
              <HomeJobHuntPulse responsiveWidth={responsiveWidth} />
              <HomeArcadeChallenge responsiveWidth={responsiveWidth} />
            </>
          ) : null}
        </View>
      );
    }

    if (item.id === 'features') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('features', e.nativeEvent.layout.y)} data-testid="home-section-features" testID="home-section-features">
          <HomeFeatureHighlights responsiveWidth={responsiveWidth} />
        </View>
      );
    }

    if (item.id === 'trophies') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('trophies', e.nativeEvent.layout.y)} data-testid="home-section-trophies" testID="home-section-trophies">
          {secondaryModulesReady ? <HomeTrophyCase responsiveWidth={responsiveWidth} /> : null}
        </View>
      );
    }

    if (item.id === 'social') {
      return (
        <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('social', e.nativeEvent.layout.y)} data-testid="home-section-social" testID="home-section-social">
          <HomeSocialProof responsiveWidth={responsiveWidth} trustCompanies={homeTrustCompanies} />
        </View>
      );
    }

    return (
      <View style={{ marginTop: sectionSpacing }} onLayout={(e) => setSectionOffset('cta', e.nativeEvent.layout.y)} data-testid="home-section-cta" testID="home-section-cta">
        <HomeCTA
          responsiveWidth={responsiveWidth}
          onStartCoaching={() => router.push('/feature-gallery')}
          onRequestDemo={() => router.push('/help')}
        />
      </View>
    );
  }, [
    colors.card,
    colors.error,
    colors.text,
    colors.warningText,
    commandDeckData,
    commandDeckLoading,
    homeNovaInlineIntro,
    responsiveWidth,
    secondaryModulesReady,
    stats,
    userName,
  ]);

  if (authLoading || !isAuthenticated) {
    return (
      <ProtectedRouteGate isLoading={authLoading} isAllowed={isAuthenticated} returnTo="/dashboard">
        <Redirect href="/dashboard" />
      </ProtectedRouteGate>
    );
  }

  if (loading || (gpsLoading && !gpsError)) {
    return (
      <AppShell>
        {loading ? (
          <HomeSkeleton />
        ) : (
          <View style={{ paddingHorizontal: 16, paddingTop: 20 }}>
            <GpsDataStatusCard
              surfaceName="home"
              loading={gpsLoading}
              error={gpsError}
              onRetry={() => void gpsRefetch()}
              colors={{
                bg: colors.bg,
                card: colors.card,
                text: colors.text,
                textSec: colors.textSec,
                textMuted: colors.textMuted,
                border: colors.border,
                borderSoft: colors.border,
                primary: colors.primary,
                error: colors.error,
                success: colors.success,
                warning: colors.warning,
              }}
              diagnostics={gpsDiagnostics}
              testIdPrefix="home"
            />
          </View>
        )}
      </AppShell>
    );
  }

  if (missingHomeLabels.length > 0 && !gpsError && gpsDiagnostics?.mode === 'live') {
    return (
      <AppShell>
        <GpsLabelBlocker surfaceName="home" missingKeys={missingHomeLabels} colors={colors} />
      </AppShell>
    );
  }

  return (
    <AppShell>
      <FadeSlideIn>
      <SafeAreaView
        style={{ flex: 1, backgroundColor: 'transparent', ...(Platform.OS === 'web' ? { maxWidth: '100vw', overflowX: 'hidden' } : {}) } as any}
        edges={['top']}
        data-testid="home-screen"
        testID="home-screen"
        onLayout={(event) => {
          const nextWidth = Math.round(Number(event?.nativeEvent?.layout?.width || 0));
          if (nextWidth > 0) {
            setHomeContentWidth((prev) => (Math.abs(prev - nextWidth) > 2 ? nextWidth : prev));
          }
        }}
      >
        {gpsError ? (
          <View
            style={{ marginHorizontal: 20, marginTop: 12 }}
            data-testid="home-inline-gps-status-wrapper"
            testID="home-inline-gps-status-wrapper"
          >
            <GpsDataStatusCard
              surfaceName="home"
              loading={false}
              error={gpsError}
              onRetry={() => void gpsRefetch()}
              colors={{
                bg: colors.bg,
                card: colors.card,
                text: colors.text,
                textSec: colors.textSec,
                textMuted: colors.textMuted,
                border: colors.border,
                borderSoft: colors.border,
                primary: colors.primary,
                error: colors.error,
                success: colors.success,
                warning: colors.warning,
              }}
              diagnostics={gpsDiagnostics}
              testIdPrefix="home"
            />
          </View>
        ) : null}

        {error && viewerIsAdmin ? (
          <View
            data-testid="home-stale-dashboard-banner" testID="home-stale-dashboard-banner"
            style={{
              marginHorizontal: 20,
              marginTop: 16,
              paddingHorizontal: 16,
              paddingVertical: 12,
              borderRadius: 14,
              backgroundColor: colors.warningSoft,
              borderWidth: 1,
              borderColor: colors.warningSoft,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <View style={{ flex: 1 }}>
              <Text style={{ color: colors.warningText, fontSize: 13, fontWeight: '800' }} data-testid="home-stale-dashboard-title" testID="home-stale-dashboard-title">
                {staleDashboardTitle}
              </Text>
              <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }} data-testid="home-stale-dashboard-subtitle" testID="home-stale-dashboard-subtitle">
                {staleDashboardSubtitle}
              </Text>
            </View>
            <TouchableOpacity onPress={refetch} style={{ paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, backgroundColor: colors.primary }} data-testid="home-stale-dashboard-retry" testID="home-stale-dashboard-retry">
              <Text style={{ color: colors.primaryText, fontSize: 12, fontWeight: '700' }} data-testid="home-stale-dashboard-retry-label" testID="home-stale-dashboard-retry-label">{staleDashboardRetry}</Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {homeRecoverableError ? (
          <View
            data-testid="home-recoverable-error-banner"
            testID="home-recoverable-error-banner"
            style={{
              marginHorizontal: 20,
              marginTop: 12,
              paddingHorizontal: 14,
              paddingVertical: 10,
              borderRadius: 12,
              backgroundColor: colors.errorSoft,
              borderWidth: 1,
              borderColor: colors.error + '35',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <Text
              style={{ color: colors.errorText, fontSize: 12, fontWeight: '700', flex: 1 }}
              data-testid="home-recoverable-error-text"
              testID="home-recoverable-error-text"
            >
              {homeRecoverableError}
            </Text>
            <TouchableOpacity
              onPress={retryHomeAuxChecks}
              style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: colors.error }}
              data-testid="home-recoverable-error-retry"
              testID="home-recoverable-error-retry"
            >
              <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
                {tx('common.retry', 'Retry')}
              </Text>
            </TouchableOpacity>
          </View>
        ) : null}
        <FlatList
          ref={scrollRef}
          data={homeVirtualItems}
          keyExtractor={(item) => item.id}
          renderItem={renderHomeSection}
          onScroll={onHomeScroll}
          onScrollToIndexFailed={onHomeScrollToIndexFailed}
          scrollEventThrottle={16}
          getItemLayout={getHomeSectionLayout}
          initialNumToRender={2}
          maxToRenderPerBatch={2}
          windowSize={5}
          removeClippedSubviews={Platform.OS !== 'web'}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
          contentContainerStyle={{ paddingBottom: 52, paddingTop: 4, paddingRight: showProgressRail ? 196 : 0 }}
          ListHeaderComponent={(
            <HomeExecutiveOverviewBand
              responsiveWidth={responsiveWidth}
              stats={stats}
              featureCount={resolvedFeatureCount}
              commandActionCount={Array.isArray(commandDeckData?.priority_actions) ? commandDeckData.priority_actions.length : 0}
              onNavigate={(route) => router.push((route || '/dashboard') as any)}
              onSectionSelect={scrollToSection}
              sections={homeSectionItems}
              isAdmin={hasAdminConsoleVisibility(user as any)}
            />
          )}
          ListFooterComponent={(
            <View style={{ alignItems: 'center', paddingVertical: 18, paddingHorizontal: 14 }}>
              <EnterpriseDisclaimerToken context="footer" testIdPrefix="home-ai-disclaimer" maxWidth={860} />
            </View>
          )}
        />

        <SectionProgressRail
          visible={showProgressRail}
          colors={colors}
          railTestId="home-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={120}
          right={14}
          items={homeSectionItems.map((item) => ({ id: item.id, label: item.label }))}
        />

        <HomeNovaAssistantWidget
          colors={colors}
          userId={user?.user_id}
          responsiveWidth={responsiveWidth}
          featureCount={resolvedFeatureCount}
          planCount={gpsState?.meta?.counts?.plans || 0}
          quickPrompts={homeNovaQuickPrompts}
          labels={homeNovaLabels}
          stackAboveTourButton={Platform.OS === 'web' && tourChecked && !tourVisible}
        />

        {/* Take Tour floating button */}
        {Platform.OS === 'web' && tourChecked && !tourVisible && (
          <div
            data-testid="take-tour-btn"
            onClick={() => {
              api.post('/home/tour-reset').catch(() => {});
              setTourVisible(true);
            }}
            style={{
              position: 'fixed', bottom: 24, right: 24, zIndex: 9990,
              width: 48, height: 48, borderRadius: 14,
              background: `linear-gradient(135deg, ${colors.card} 0%, ${colors.bg} 100%)`,
              border: `1px solid ${colors.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              cursor: 'pointer',
              boxShadow: `0 4px 16px ${colors.overlay}`,
              transition: 'transform 0.2s ease, box-shadow 0.2s ease',
            } as any}
            onMouseEnter={(e: any) => { e.currentTarget.style.transform = 'translateY(-2px) scale(1.05)'; e.currentTarget.style.boxShadow = `0 8px 24px ${colors.primary}40`; }}
            onMouseLeave={(e: any) => { e.currentTarget.style.transform = 'translateY(0) scale(1)'; e.currentTarget.style.boxShadow = `0 4px 16px ${colors.overlay}`; }}
            title={takeTourTitle}
          >
            <Ionicons name="help-circle-outline" size={22} color={colors.primary} />
          </div>
        )}

        {/* Onboarding Tour Overlay */}
        <HomeOnboardingTour
          visible={tourVisible}
          onComplete={() => setTourVisible(false)}
        />

        {/* Onboarding Wizard — shown only for first-time sign-up users */}
        <OnboardingWizard
          visible={wizardVisible}
          onClose={() => {
            setWizardVisible(false);
            api.post('/onboarding-wizard/dismiss').catch(() => {});
          }}
        />

        {/* "Continue where you left off?" prompt — web-only, session-scoped */}
        <HomeContinueToast />
      </SafeAreaView>
      </FadeSlideIn>
    </AppShell>
  );
}