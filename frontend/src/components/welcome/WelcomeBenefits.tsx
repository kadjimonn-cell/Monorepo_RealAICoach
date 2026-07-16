import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Platform, Animated,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '../../context/ThemeContext';
import { StaggerChildren } from '../StaggerChildren';
import { getShadow } from '../../utils/themeShadows';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGlobalPlatformState } from '../../hooks/useGlobalPlatformState';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import type { GLSTokens } from '../../context/GLSContext';
import { withAlpha } from '../../utils/colorAlpha';
import { useAccessControl } from '../../context/AccessControlContext';
import { useAuth } from '../../context/AuthContext';
import { resolveVisitorCtaPath } from '../../utils/visitorCtaPolicy';
import { CAPABILITY_CATEGORY_ORDER, CAPABILITY_TIER_RANK, hydrateCapabilityCatalog, type CapabilityBadgeId, type CapabilityCategoryId, type CapabilityTier } from './welcomeCapabilityCatalog';
import { WelcomeCapabilitySpotlight } from './WelcomeCapabilitySpotlight';
import { WelcomeCapabilityProofRail } from './WelcomeCapabilityProofRail';
import { WelcomeCapabilityMatrix } from './WelcomeCapabilityMatrix';
import { loadWelcomeWorkflowMemory, persistWelcomeWorkflowMemory } from './welcomeWorkflowMemory';
import { WELCOME_CENTERED_LAYOUT_BREAKPOINT, WELCOME_CENTERED_SECTION_MAX_WIDTH } from './welcomeSectionContract';

type WelcomeBenefitsProps = {
  onDecisionPathSignal?: (areaId: 'features' | 'pricing' | 'social-proof', weight?: number) => void;
};

export function WelcomeBenefits({ onDecisionPathSignal }: WelcomeBenefitsProps) {
  const router = useRouter();
  const { width, isDesktop, isTablet, padding, tokens } = useGLSBreakpoint();
  const isCompactMobile = width < 560;
  const useDenseMobileCapabilityCards = width < 430;
  const isCompactTablet = width < 980;
  const useWideCapabilityLayout = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT;
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t, languageCode } = useLanguage();
  const { user } = useAuth();
  const { state: gpsState, counts } = useGlobalPlatformState();
  const { effectivePlan, canAccessRoute } = useAccessControl();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const s = useMemo(() => makeStyles(WC, isDark, padding, tokens, width), [isDark, languageCode, padding, tokens, width]);

  const fadeA = useRef(new Animated.Value(0)).current;
  const slideA = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeA, { toValue: 1, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideA, { toValue: 0, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const allCapabilities = useMemo(() => hydrateCapabilityCatalog(gpsState?.features), [gpsState?.features]);
  const categories = useMemo(
    () => CAPABILITY_CATEGORY_ORDER.map((id) => ({
      id,
      label: tx(`welcome.features.categories.${id}`, id),
    })),
    [tx],
  );
  const [activeCategory, setActiveCategory] = useState<CapabilityCategoryId>('growth');
  const [selectedCapabilityId, setSelectedCapabilityId] = useState('ai-chatbot');
  const [workflowMemoryReady, setWorkflowMemoryReady] = useState(false);
  const [workflowMemoryRecencyLabel, setWorkflowMemoryRecencyLabel] = useState('');

  const currentPlan: CapabilityTier = useMemo(() => {
    if (!user) return 'free';
    return (effectivePlan || 'free') as CapabilityTier;
  }, [effectivePlan, user]);

  const categoryCapabilities = useMemo(
    () => allCapabilities.filter((item) => item.categoryId === activeCategory),
    [activeCategory, allCapabilities],
  );

  useEffect(() => {
    if (!categoryCapabilities.some((item) => item.featureId === selectedCapabilityId)) {
      setSelectedCapabilityId(categoryCapabilities[0]?.featureId || 'ai-chatbot');
    }
  }, [categoryCapabilities, selectedCapabilityId]);

  useEffect(() => {
    let cancelled = false;
    const restoreMemory = async () => {
      const memory = await loadWelcomeWorkflowMemory();
      if (cancelled) return;
      if (memory?.categoryId && CAPABILITY_CATEGORY_ORDER.includes(memory.categoryId as CapabilityCategoryId)) {
        setActiveCategory(memory.categoryId as CapabilityCategoryId);
      }
      if (memory?.featureId) {
        setSelectedCapabilityId(memory.featureId);
      }
      if (memory?.updatedAt) {
        const timestamp = Date.parse(memory.updatedAt);
        if (Number.isFinite(timestamp)) {
          const deltaMin = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
          const label = deltaMin < 1
            ? tx('welcome.features.memory.justNow', 'just now')
            : deltaMin < 60
              ? tx('welcome.features.memory.minutesAgo', '{count}m ago').replace('{count}', String(deltaMin))
              : tx('welcome.features.memory.hoursAgo', '{count}h ago').replace('{count}', String(Math.floor(deltaMin / 60)));
          setWorkflowMemoryRecencyLabel(label);
        }
      }
      setWorkflowMemoryReady(true);
    };

    void restoreMemory();
    return () => {
      cancelled = true;
    };
  }, [tx]);

  const selectedCapability = useMemo(
    () => categoryCapabilities.find((item) => item.featureId === selectedCapabilityId) || categoryCapabilities[0] || allCapabilities[0],
    [allCapabilities, categoryCapabilities, selectedCapabilityId],
  );

  const accessibleForTier = useCallback((tier: CapabilityTier) => {
    return CAPABILITY_TIER_RANK[currentPlan] >= CAPABILITY_TIER_RANK[tier];
  }, [currentPlan]);

  const accessibleCount = useMemo(
    () => allCapabilities.filter((item) => accessibleForTier(item.tier)).length,
    [accessibleForTier, allCapabilities],
  );
  const lockedCount = Math.max(0, allCapabilities.length - accessibleCount);

  const badgeLabel = useCallback((badgeId: CapabilityBadgeId) => tx(`welcome.features.badges.${badgeId}`, badgeId.replace('-', ' ')), [tx]);
  const tierLabel = useCallback((tier: CapabilityTier) => tx(`welcome.features.tiers.${tier}`, tier), [tx]);

  const titleForFeature = useCallback((featureId: string, fallback: string) => tx(`welcome.features.catalog.${featureId}.title`, fallback), [tx]);
  const summaryForFeature = useCallback((featureId: string, fallback: string) => tx(`welcome.features.catalog.${featureId}.summary`, fallback), [tx]);

  const capabilityViews = useMemo(() => allCapabilities.map((item) => {
    const access = canAccessRoute(item.route);
    const isAccessibleNow = Boolean(user) ? access.allowed : false;
    return {
      ...item,
      title: titleForFeature(item.featureId, item.titleFallback),
      summary: summaryForFeature(item.featureId, item.summaryFallback),
      badgeLabel: badgeLabel(item.badgeId),
      tierLabel: tierLabel(item.tier),
      accessLabel: access.allowed ? tx('welcome.features.state.live', 'Open now') : tx(`welcome.features.unlockHint.${item.tier}`, `Unlock ${tierLabel(item.tier)}`),
      isAccessibleNow,
      isSelected: item.featureId === selectedCapability?.featureId,
    };
  }), [allCapabilities, badgeLabel, canAccessRoute, selectedCapability?.featureId, summaryForFeature, tierLabel, titleForFeature, tx, user]);

  const selectedCapabilityView = useMemo(
    () => capabilityViews.find((item) => item.featureId === selectedCapability?.featureId) || capabilityViews[0],
    [capabilityViews, selectedCapability?.featureId],
  );

  useEffect(() => {
    if (!workflowMemoryReady || !selectedCapabilityView) return;
    void persistWelcomeWorkflowMemory({
      featureId: selectedCapabilityView.featureId,
      categoryId: selectedCapabilityView.categoryId,
      updatedAt: new Date().toISOString(),
    });
  }, [selectedCapabilityView, workflowMemoryReady]);

  useEffect(() => {
    if (!workflowMemoryReady) return;
    onDecisionPathSignal?.('features', 2);
  }, [activeCategory, onDecisionPathSignal, workflowMemoryReady]);

  const trustNames = useMemo(
    () => (Array.isArray(gpsState?.messaging?.trust_names) ? gpsState.messaging.trust_names.map((name: any) => String(name || '').trim()).filter(Boolean).slice(0, 4) : []),
    [gpsState?.messaging],
  );
  const testimonialsCount = useMemo(
    () => Array.isArray(gpsState?.messaging?.welcome_testimonials) ? gpsState.messaging.welcome_testimonials.length : 0,
    [gpsState?.messaging],
  );

  const proofItems = useMemo(() => ([
    {
      id: 'live-capabilities',
      icon: 'sparkles-outline',
      label: tx('welcome.features.proof.liveCapabilities', 'Live capabilities'),
      value: tx('welcome.features.proof.liveCapabilitiesValue', '{count} active workflows').replace('{count}', String(Math.max(counts.features || allCapabilities.length, allCapabilities.length))),
    },
    {
      id: 'proof-stories',
      icon: 'people-outline',
      label: tx('welcome.features.proof.proofStories', 'Proof stories'),
      value: tx('welcome.features.proof.proofStoriesValue', '{count} enterprise testimonials').replace('{count}', String(Math.max(testimonialsCount, 10))),
    },
    {
      id: 'guided-answers',
      icon: 'help-buoy-outline',
      label: tx('welcome.features.proof.guidedAnswers', 'Guided answers'),
      value: tx('welcome.features.proof.guidedAnswersValue', '{count} FAQ playbooks').replace('{count}', String(Math.max(counts.faq || 0, 20))),
    },
    {
      id: 'plan-layers',
      icon: 'layers-outline',
      label: tx('welcome.features.proof.planLayers', 'Unlock depth'),
      value: tx('welcome.features.proof.planLayersValue', '{count} subscription layers').replace('{count}', String(Math.max(counts.plans || 0, 3))),
    },
    {
      id: 'trust-signal',
      icon: 'shield-checkmark-outline',
      label: tx('welcome.features.proof.trustSignal', 'Trust signal'),
      value: trustNames.length > 0 ? trustNames.join(' • ') : tx('welcome.features.proof.trustSignalFallback', 'Governance-ready operating surface'),
    },
  ]), [allCapabilities.length, counts.faq, counts.features, counts.plans, testimonialsCount, trustNames, tx]);

  const categoryTrackItems = useMemo(
    () => categoryCapabilities.map((item) => ({
      id: item.featureId,
      label: titleForFeature(item.featureId, item.titleFallback),
      state: accessibleForTier(item.tier) && Boolean(user) ? 'live' as const : 'locked' as const,
    })),
    [accessibleForTier, categoryCapabilities, titleForFeature, user],
  );

  const buildUpgradePath = useCallback((tier: CapabilityTier, featureId: string) => {
    const params = new URLSearchParams();
    params.set('upgrade_from', 'welcome_capability_command_center');
    params.set('recommended_plan', tier);
    params.set('upgrade_context', featureId);
    params.set('upgrade_title', tx('welcome.features.upgradeTitle', 'Unlock the full capability command center'));
    return `/subscription/plans?${params.toString()}`;
  }, [tx]);

  const buildComparePlansPath = useCallback(() => resolveVisitorCtaPath(
    '/subscription/plans?upgrade_from=welcome_capability_command_center_compare',
    {
      isAuthenticated: Boolean(user),
      surface: 'welcome',
      fallbackPath: '/auth/register?source=welcome-capability-command-center-compare&return_to=%2Fwelcome%3Fsection%3Dpricing',
    },
  ), [user]);

  const launchCapability = useCallback((featureId: string) => {
    onDecisionPathSignal?.('features', 3);
    const item = allCapabilities.find((entry) => entry.featureId === featureId);
    if (!item) return;

    if (!user) {
      const target = resolveVisitorCtaPath('/auth/register?source=welcome-capability-command-center&return_to=%2Fwelcome%3Fsection%3Dfeatures', {
        isAuthenticated: false,
        surface: 'welcome',
        fallbackPath: '/welcome?section=features',
      });
      router.push(target as any);
      return;
    }

    const decision = canAccessRoute(item.route);
    if (decision.allowed) {
      router.push(item.route as any);
      return;
    }

    if (decision.redirectTo === '/subscription/plans') {
      router.push(buildUpgradePath(item.tier, item.featureId) as any);
      return;
    }

    router.push((decision.redirectTo || '/dashboard') as any);
  }, [allCapabilities, buildUpgradePath, canAccessRoute, onDecisionPathSignal, router, user]);

  const primaryCtaLabel = useMemo(() => {
    if (!selectedCapabilityView) return tx('welcome.features.cta.createFree', 'Create free account');
    if (!user) return tx('welcome.features.cta.createFree', 'Create free account');
    if (selectedCapabilityView.isAccessibleNow) return tx('welcome.features.cta.openWorkspace', 'Open workspace');
    return selectedCapabilityView.tier === 'premium'
      ? tx('welcome.features.cta.unlockPremium', 'Unlock Premium')
      : tx('welcome.features.cta.unlockBasic', 'Unlock Basic');
  }, [selectedCapabilityView, tx, user]);

  const spotlightPlanLabel = useMemo(() => {
    if (!user) return tx('welcome.features.plan.visitor', 'Visitor preview');
    return tx(`welcome.features.plan.${currentPlan}`, currentPlan);
  }, [currentPlan, tx, user]);

  const memoryHeadline = useMemo(() => {
    if (!workflowMemoryReady) return tx('welcome.features.memory.loading', 'Restoring your last workflow view…');
    if (workflowMemoryRecencyLabel) {
      return tx('welcome.features.memory.returning', 'Recommended next workflow • last viewed {time}').replace('{time}', workflowMemoryRecencyLabel);
    }
    return tx('welcome.features.memory.fresh', 'Recommended next workflow');
  }, [tx, workflowMemoryReady, workflowMemoryRecencyLabel]);

  const spotlightSummary = useMemo(() => {
    if (!selectedCapabilityView) return tx('welcome.features.commandCenterSubtitle', 'See what unlocks next.');
    const featureSummary = selectedCapabilityView.summary;
    if (!user) {
      return `${featureSummary} ${tx('welcome.features.planCopy.visitor', 'Create a free account to save this command center and activate your first guided workflow.')}`;
    }
    if (selectedCapabilityView.isAccessibleNow) {
      return `${featureSummary} ${tx('welcome.features.planCopy.live', 'You can launch this workflow now and keep the rest of the command center as your upgrade map.')}`;
    }
    if (currentPlan === 'free') {
      return `${featureSummary} ${tx('welcome.features.planCopy.free', 'Basic unlocks the broader workflow bench, while Premium adds the highest-control enterprise layers.')}`;
    }
    return `${featureSummary} ${tx('welcome.features.planCopy.basic', 'Premium unlocks the final command layer, deeper governance, and the most defensible operational leverage.')}`;
  }, [currentPlan, selectedCapabilityView, tx, user]);

  return (
    <Animated.View
      style={[s.wrap, { opacity: fadeA, transform: [{ translateY: slideA }] }]}
      data-testid="welcome-benefits" testID="welcome-benefits"
    >
      <View style={s.headerBlock} data-testid="welcome-capability-header-block" testID="welcome-capability-header-block">
        <Text style={s.label} data-testid="welcome-benefits-label" testID="welcome-benefits-label">{tx('welcome.features.commandCenterLabel', 'Capability Command Center')}</Text>
        <Text style={[s.title, isDesktop && { fontSize: 38 }]} data-testid="welcome-benefits-title" testID="welcome-benefits-title">
          {tx('welcome.features.commandCenterTitle', 'See which AI workflows drive speed, clarity, and paid-value depth.')}
        </Text>
        <Text style={[s.sub, isCompactMobile && { marginBottom: 30 }]} data-testid="welcome-benefits-subtitle" testID="welcome-benefits-subtitle">
          {tx('welcome.features.commandCenterSubtitle', 'Browse the platform like a serious buyer: by outcomes, unlock depth, and the next best workflow to activate.')}
        </Text>
      </View>

      <StaggerChildren staggerMs={110} distance={28}>
        {selectedCapabilityView ? (
          <View style={s.commandCenterShell} data-testid="welcome-capability-command-center" testID="welcome-capability-command-center">
            <WelcomeCapabilitySpotlight
              colors={WC}
              isDark={isDark}
              isDesktop={isDesktop}
              isTablet={isTablet}
              compact={isCompactTablet}
              wideLayout={useWideCapabilityLayout}
              title={tx('welcome.features.spotlightLabel', 'Executive spotlight')}
              subtitle={tx('welcome.features.spotlightMetric', 'Catalog in focus')}
              planLabel={`${spotlightPlanLabel} • ${memoryHeadline}`}
              selectedCapability={selectedCapabilityView}
              badgeLabel={selectedCapabilityView.badgeLabel}
              categoryLabel={tx(`welcome.features.categories.${selectedCapabilityView.categoryId}`, selectedCapabilityView.categoryId)}
              tierLabel={selectedCapabilityView.tierLabel}
              accessibleNowLabel={tx('welcome.features.metrics.accessibleNow', 'Available now')}
              lockedLabel={tx('welcome.features.metrics.lockedNext', 'Locked next')}
              spotlightSummary={spotlightSummary}
              primaryCtaLabel={primaryCtaLabel}
              secondaryCtaLabel={tx('welcome.features.cta.comparePlans', 'Compare plans')}
              onPrimaryPress={() => launchCapability(selectedCapabilityView.featureId)}
              onSecondaryPress={() => {
                onDecisionPathSignal?.('pricing', 2);
                router.push(buildComparePlansPath() as any);
              }}
              accessibleCount={accessibleCount}
              lockedCount={lockedCount}
              totalCount={allCapabilities.length}
              playbooksLabel={tx('welcome.features.board.playbooks', 'Guided playbooks')}
              playbooksValue={tx('welcome.features.board.playbooksValue', '{count} live').replace('{count}', String(Math.max(counts.faq || 0, 20)))}
              workflowLabel={tx('welcome.features.board.workflow', 'Next best move')}
              workflowValue={selectedCapabilityView.title}
              trackItems={categoryTrackItems}
              trackLiveLabel={tx('welcome.features.state.live', 'Live')}
              trackLockedLabel={tx('welcome.features.state.locked', 'Locked')}
            />

            <WelcomeCapabilityProofRail
              colors={WC}
              isDark={isDark}
              width={width}
              wideLayout={useWideCapabilityLayout}
              title={tx('welcome.features.proof.title', 'Enterprise proof lane')}
              items={proofItems}
            />

            <WelcomeCapabilityMatrix
              colors={WC}
              isDark={isDark}
              isDesktop={isDesktop}
              isTablet={isTablet}
              compact={isCompactTablet}
              denseMobile={useDenseMobileCapabilityCards}
              roomyDesktop={useWideCapabilityLayout}
              title={tx('welcome.features.matrixLabel', 'Interactive capability matrix')}
              subtitle={tx('welcome.features.matrixSubtitle', 'Switch categories, inspect unlock depth, and jump directly into the workflows your teams will keep returning to.')}
              categories={categories}
              activeCategory={activeCategory}
              items={capabilityViews.filter((item) => item.categoryId === activeCategory)}
              liveLabel={tx('welcome.features.state.live', 'Live')}
              lockedHint={tx('welcome.features.lockedHint', 'Upgrade to activate this command lane.')}
              ctaLabel={tx('welcome.features.cta.openWorkspace', 'Open workspace')}
              onCategoryChange={setActiveCategory}
              onFocusItem={(featureId) => {
                onDecisionPathSignal?.('features', 1);
                setSelectedCapabilityId(featureId);
              }}
              onActionItem={launchCapability}
            />
          </View>
        ) : (
          <View style={s.emptyCard} data-testid="welcome-benefits-empty" testID="welcome-benefits-empty">
            <Text style={s.emptyTitle}>{tx('welcome.benefits.empty', 'Empty')}</Text>
          </View>
        )}
      </StaggerChildren>

      <View style={{ display: 'none' }} data-testid="welcome-workflow-memory-context" testID="welcome-workflow-memory-context">
        <Text>{selectedCapabilityView?.title || ''}</Text>
        <Text>{tx(`welcome.features.categories.${selectedCapabilityView?.categoryId || 'growth'}`, selectedCapabilityView?.categoryId || 'growth')}</Text>
        <Text>{workflowMemoryRecencyLabel}</Text>
      </View>
    </Animated.View>
  );
}

function makeStyles(WC: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens, width: number) {
  const contentHorizontalPadding = width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT ? Math.max(24, horizontalPadding - 14) : horizontalPadding;
  return StyleSheet.create({
    wrap: {
      paddingHorizontal: contentHorizontalPadding,
      paddingVertical: 80,
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      width: '100%',
      ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}),
    },
    headerBlock: {
      alignItems: 'center',
      marginBottom: 26,
      gap: 0,
    },
    label: { color: WC.indigoText, fontSize: 11, fontWeight: '800', letterSpacing: 2.5, textAlign: 'center', marginBottom: 14 },
    title: { color: WC.text, fontSize: width < 420 ? 31 : 34, fontWeight: '900', textAlign: 'center', letterSpacing: -1.1, marginBottom: 14, maxWidth: 980 },
    sub: { color: WC.textMuted, fontSize: 16, textAlign: 'center', lineHeight: 26, maxWidth: 760, alignSelf: 'center', marginBottom: 0 },
    commandCenterShell: {
      gap: 18,
      width: '100%',
      maxWidth: width >= WELCOME_CENTERED_LAYOUT_BREAKPOINT ? WELCOME_CENTERED_SECTION_MAX_WIDTH : undefined,
      alignSelf: 'center',
    },
    emptyCard: {
      borderRadius: 24,
      borderWidth: 1,
      borderColor: WC.border,
      backgroundColor: withAlpha(WC.surface, isDark ? 'EE' : 'FA'),
      padding: 24,
      ...getShadow('md', isDark),
    },
    emptyTitle: {
      color: WC.text,
      fontSize: 18,
      fontWeight: '800',
      textAlign: 'center',
    },
  });
}