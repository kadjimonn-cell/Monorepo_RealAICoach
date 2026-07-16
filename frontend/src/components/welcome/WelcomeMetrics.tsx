import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, Platform, Animated, TouchableOpacity,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useLiveMetrics, type GrowthIntelligencePoint } from '../../hooks/useLiveMetrics';
import { AnimatedCounter } from '../AnimatedCounter';
import { getShadow } from '../../utils/themeShadows';
import { useLanguage } from '../../i18n/LanguageContext';
import { useGLSBreakpoint } from '../layout/GlobalLayoutSystem';
import type { GLSTokens } from '../../context/GLSContext';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
import { useAccessControl } from '../../context/AccessControlContext';
import { useAuth } from '../../context/AuthContext';
import { resolveVisitorCtaPath } from '../../utils/visitorCtaPolicy';
import { withAlpha } from '../../utils/colorAlpha';

let Recharts: any = null;
if (Platform.OS === 'web') {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    Recharts = require('recharts');
  } catch (error) {
    handleAppRecoverableError({
      scope: 'src/components/welcome/WelcomeMetrics.tsx#recharts',
      error,
      message: 'Something went wrong. Please retry.',
      notifyMode: 'silent',
    });
  }
}

const RANGE_OPTIONS = [
  { id: '30d', label: '30D' },
  { id: '90d', label: '90D' },
  { id: '12m', label: '12M' },
] as const;

function ensureGrowthCSS(theme: any) {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;
  const id = 'welcome-growth-intelligence-css';
  const existing = document.getElementById(id) as HTMLStyleElement | null;
  const css = `
@keyframes welcome-growth-glow {
  0%, 100% { box-shadow: 0 0 0 ${withAlpha(theme.accent, '00')}; }
  50% { box-shadow: 0 0 28px ${withAlpha(theme.accent, '24')}; }
}
[data-testid="performance-badge"] {
  animation: welcome-growth-glow 2.8s ease-in-out infinite;
}
@media (max-width: 559px) {
  [data-testid="growth-chart-tooltip"] {
    display: none !important;
  }
}
`;
  if (existing) {
    if (existing.textContent !== css) {
      existing.textContent = css;
    }
    return;
  }
  const style = document.createElement('style');
  style.id = id;
  style.textContent = css;
  document.head.appendChild(style);
}

function formatCompact(value: number) {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return `${value}`;
}

function ChartTooltip({ active, payload, label, theme, comparisonLabel, compact }: any) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload || {};
  const locale = (globalThis as any).__racWelcomeMetricsLocale || {};
  const text = (key: string, fallback: string) => locale?.[key] || fallback;
  const tooltipMinWidth = compact ? 176 : 210;
  const tooltipPadding = compact ? '10px 12px' : '12px 14px';
  const valueFontSize = compact ? 20 : 24;
  const metaGridColumns = compact ? '1fr' : '1fr 1fr';
  return (
    <div
      data-testid="growth-chart-tooltip"
      style={{
        background: theme.tooltipBg,
        border: `1px solid ${theme.borderStrong}`,
        borderRadius: 14,
        padding: tooltipPadding,
        minWidth: tooltipMinWidth,
        maxWidth: compact ? 190 : 240,
        boxShadow: `0 18px 44px ${theme.shadow}`,
        color: theme.text,
      }}
    >
      <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', color: theme.textMuted, fontSize: 11, letterSpacing: '0.18em', textTransform: 'uppercase', marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: 'Outfit, sans-serif', fontSize: valueFontSize, fontWeight: 800, letterSpacing: '-0.04em', color: theme.text }}>{point.growth_score}%</div>
      <div style={{ fontFamily: 'IBM Plex Sans, sans-serif', color: theme.textSec, fontSize: 12, marginTop: 4 }}>{comparisonLabel}: {point.benchmark_score}%</div>
      <div style={{ display: 'grid', gridTemplateColumns: metaGridColumns, gap: compact ? 6 : 8, marginTop: 12 }}>
        <div>
          <div style={{ color: theme.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em' }}>{text('users', 'Users')}</div>
          <div style={{ color: theme.text, fontSize: 13, fontWeight: 700 }}>{formatCompact(Number(point.active_users || 0))}</div>
        </div>
        <div>
          <div style={{ color: theme.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em' }}>{text('sessions', 'Sessions')}</div>
          <div style={{ color: theme.text, fontSize: 13, fontWeight: 700 }}>{formatCompact(Number(point.ai_sessions || 0))}</div>
        </div>
        <div>
          <div style={{ color: theme.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em' }}>{text('completion', 'Completion')}</div>
          <div style={{ color: theme.text, fontSize: 13, fontWeight: 700 }}>{point.completion_rate}%</div>
        </div>
        <div>
          <div style={{ color: theme.textMuted, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em' }}>{text('velocity', 'Velocity')}</div>
          <div style={{ color: theme.text, fontSize: 13, fontWeight: 700 }}>{point.conversion_velocity}%</div>
        </div>
      </div>
      {point?.milestone?.title ? (
        <div style={{ marginTop: 12, borderTop: `1px solid ${theme.border}`, paddingTop: 10 }}>
          <div style={{ color: theme.accent, fontSize: 11, fontWeight: 700 }}>{point.milestone.title}</div>
          <div style={{ color: theme.textMuted, fontSize: 11, marginTop: 2 }}>{point.milestone.impact_label}</div>
        </div>
      ) : null}
    </div>
  );
}

function EmptySparkline({ styles, theme, title, subtitle }: { styles: any; theme: any; title: string; subtitle: string }) {
  return (
    <View style={styles.emptyCard} data-testid="growth-chart-empty" testID="growth-chart-empty">
      <Ionicons name="analytics-outline" size={24} color={theme.textMuted} />
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptySub}>{subtitle}</Text>
    </View>
  );
}

export function WelcomeMetrics() {
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const { darkMode: isDark, colors: WC } = useTheme();
  const { t } = useLanguage();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { canAccessPlan } = useAccessControl();
  const useSplitGrowthLayout = width >= 1180;
  const isCompactGrowthLayout = width < 980;
  const isPhoneLayout = width < 560;
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const styles = useMemo(() => makeStyles(WC, isDark, padding, tokens, width, isDesktop, useSplitGrowthLayout), [WC, isDark, padding, tokens, width, isDesktop, useSplitGrowthLayout]);
  const { vanity, data } = useLiveMetrics(3000);

  useEffect(() => {
    (globalThis as any).__racWelcomeMetricsLocale = {
      users: tx('welcome.metrics.tooltip.users', 'Users'),
      sessions: tx('welcome.metrics.tooltip.sessions', 'Sessions'),
      completion: tx('welcome.metrics.tooltip.completion', 'Completion'),
      velocity: tx('welcome.metrics.tooltip.velocity', 'Velocity'),
    };
  }, [tx]);

  const fadeA = useRef(new Animated.Value(0)).current;
  const slideA = useRef(new Animated.Value(40)).current;

  useEffect(() => {
    ensureGrowthCSS(WC);
    Animated.parallel([
      Animated.timing(fadeA, { toValue: 1, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
      Animated.timing(slideA, { toValue: 0, duration: 900, delay: 100, useNativeDriver: Platform.OS !== 'web' }),
    ]).start();
  }, [WC, fadeA, slideA]);

  const growthIntelligence = data?.growth_intelligence;
  const defaultRange = (growthIntelligence?.default_range || '90d') as '30d' | '90d' | '12m';
  const [selectedRange, setSelectedRange] = useState<'30d' | '90d' | '12m'>(defaultRange);

  useEffect(() => {
    setSelectedRange(defaultRange);
  }, [defaultRange]);

  const activeRange = growthIntelligence?.ranges?.[selectedRange] || growthIntelligence?.ranges?.[defaultRange];
  const chartData = activeRange?.points || [];
  const hasBasicPlan = isAuthenticated && canAccessPlan('basic');
  const hasPremiumPlan = isAuthenticated && canAccessPlan('premium');
  const planState: 'visitor' | 'free' | 'basic' | 'premium' = !isAuthenticated
    ? 'visitor'
    : hasPremiumPlan
      ? 'premium'
      : hasBasicPlan
        ? 'basic'
        : 'free';
  const strongestPeriodLabel = activeRange?.strongest_period_label || '—';
  const weakestPeriodLabel = activeRange?.weakest_period_label || '—';
  const confidenceScore = growthIntelligence?.confidence?.score ?? Math.max(76, Math.min(99, Number(vanity?.system_health || 0)));
  const headlineValue = growthIntelligence?.headline_metric?.value ?? Number(vanity?.performance_boost || 0);
  const deltaVsBaseline = growthIntelligence?.headline_metric?.delta_vs_baseline ?? Math.max(8, Math.round(headlineValue * 0.22));
  const latestPoint = chartData[chartData.length - 1] || null;
  const firstPoint = chartData[0] || null;
  const forecastConfidenceValue = Math.max(76, Math.min(98, Math.round((confidenceScore * 0.72) + ((latestPoint?.completion_rate || 78) * 0.28))));
  const benchmarkCorrelationValue = Math.max(0.62, Math.min(0.96, 0.66 + (((latestPoint?.growth_score || headlineValue) - (firstPoint?.benchmark_score || 42)) / 180))).toFixed(2);
  const upsideWindowValue = Math.max(9, Math.min(28, (activeRange?.momentum_delta || 12) + 8));

  const benchmarkPersonalization = useMemo(() => {
    if (planState === 'visitor') {
      return {
        label: tx('welcome.metrics.benchmark.visitorLabel', 'Public benchmark preview'),
        story: tx('welcome.metrics.benchmark.visitorStory', 'Preview how public platform momentum compares with an anonymized benchmark before you create an account.'),
        compactStory: tx('welcome.metrics.benchmark.visitorCompact', 'Preview the public benchmark before you create an account.'),
      };
    }
    if (planState === 'free') {
      return {
        label: tx('welcome.metrics.benchmark.freeLabel', 'Basic benchmark preview'),
        story: tx('welcome.metrics.benchmark.freeStory', 'Basic unlocks forecast confidence. Premium adds the full benchmark-correlation layer and upside storytelling.'),
        compactStory: tx('welcome.metrics.benchmark.freeCompact', 'Basic unlocks forecast confidence. Premium adds benchmark correlation.'),
      };
    }
    if (planState === 'basic') {
      return {
        label: tx('welcome.metrics.benchmark.basicLabel', 'Premium benchmark unlock'),
        story: tx('welcome.metrics.benchmark.basicStory', `Your forecast is live. Premium adds correlation depth around ${strongestPeriodLabel} and next-window upside confidence.`),
        compactStory: tx('welcome.metrics.benchmark.basicCompact', `Premium adds deeper correlation around ${strongestPeriodLabel}.`),
      };
    }
    return {
      label: tx('welcome.metrics.benchmark.premiumLabel', 'Your premium benchmark correlation'),
      story: tx('welcome.metrics.benchmark.premiumStory', `Correlation intelligence is live — strongest around ${strongestPeriodLabel}, with watchpoints around ${weakestPeriodLabel}.`),
      compactStory: tx('welcome.metrics.benchmark.premiumCompact', `Correlation intelligence is live — strongest around ${strongestPeriodLabel}.`),
    };
  }, [planState, strongestPeriodLabel, tx, weakestPeriodLabel]);
  const comparisonLabel = benchmarkPersonalization.label;
  const benchmarkStoryText = isCompactGrowthLayout ? benchmarkPersonalization.compactStory : benchmarkPersonalization.story;

  const goToPlanUpgrade = useCallback((recommendedPlan: 'basic' | 'premium', upgradeTitle: string) => {
    const safeTarget = resolveVisitorCtaPath(
      `/subscription/plans?upgrade_from=%2Fwelcome&upgrade_reason=growth_intelligence_unlock&recommended_plan=${recommendedPlan}&upgrade_context=growth_intelligence&upgrade_title=${encodeURIComponent(upgradeTitle)}`,
      {
        isAuthenticated,
        surface: 'welcome',
        fallbackPath: '/auth/register?source=welcome-growth-intelligence&return_to=%2Fwelcome%3Fsection%3Dpricing',
      },
    );
    router.push(safeTarget as any);
  }, [isAuthenticated, router]);

  const conversionStrip = useMemo(() => {
    if (planState === 'visitor') {
      return {
        stateLabel: tx('welcome.metrics.plan.visitor.stateLabel', 'Preview mode'),
        title: tx('welcome.metrics.plan.visitor.title', 'Unlock forecast confidence and benchmark correlation'),
        copy: tx('welcome.metrics.plan.visitor.copy', 'Create a free account to save this live intelligence preview. Basic unlocks forecast confidence; Premium unlocks benchmark correlation and upside windows.'),
        ctaLabel: tx('welcome.metrics.plan.visitor.cta', 'Start free'),
        previewEyebrow: tx('welcome.metrics.plan.visitor.eyebrow', 'Conversion preview'),
        inlineCopy: tx('welcome.metrics.plan.visitor.inlineCopy', 'Start free to save this intelligence preview, then upgrade when you want benchmark correlation and forecast confidence.'),
        destinationLabel: tx('welcome.metrics.plan.visitor.destinationLabel', 'Destination · Create account'),
        destinationHint: tx('welcome.metrics.plan.visitor.destinationHint', 'Starts a free account and returns you to your first premium forecast setup path.'),
        compactTitle: tx('welcome.metrics.plan.visitor.compactTitle', 'Unlock forecast + correlation'),
        compactCopy: tx('welcome.metrics.plan.visitor.compactCopy', 'Create a free account to save this preview. Premium adds correlation and upside windows.'),
        compactDestinationHint: tx('welcome.metrics.plan.visitor.compactDestinationHint', 'Create an account and return here to continue.'),
        onPress: () => router.push('/auth/register?source=welcome-growth-intelligence&return_to=%2Fwelcome%3Fsection%3Dpricing' as any),
      };
    }
    if (planState === 'free') {
      return {
        stateLabel: tx('welcome.metrics.plan.free.stateLabel', 'Free plan'),
        title: tx('welcome.metrics.plan.free.title', 'Upgrade to Basic to unlock forecast confidence'),
        copy: tx('welcome.metrics.plan.free.copy', 'You are seeing the public intelligence preview. Basic reveals forecast confidence and unlocks deeper momentum storytelling; Premium adds benchmark correlation and upside windows.'),
        ctaLabel: tx('welcome.metrics.plan.free.cta', 'Upgrade to Basic'),
        previewEyebrow: tx('welcome.metrics.plan.free.eyebrow', 'Basic unlock'),
        inlineCopy: tx('welcome.metrics.plan.free.inlineCopy', 'Free users can preview the growth story, but Basic is required to unlock forecast confidence and richer intelligence depth.'),
        destinationLabel: tx('welcome.metrics.plan.free.destinationLabel', 'Destination · Subscription plans'),
        destinationHint: tx('welcome.metrics.plan.free.destinationHint', 'Opens plans with a Basic recommendation and growth-intelligence upgrade context.'),
        compactTitle: tx('welcome.metrics.plan.free.compactTitle', 'Upgrade to Basic for live forecast confidence'),
        compactCopy: tx('welcome.metrics.plan.free.compactCopy', 'Basic unlocks forecast confidence. Premium adds correlation and upside windows.'),
        compactDestinationHint: tx('welcome.metrics.plan.free.compactDestinationHint', 'Opens plans with a Basic recommendation.'),
        onPress: () => goToPlanUpgrade('basic', 'Unlock Growth Intelligence Forecasts'),
      };
    }
    if (planState === 'basic') {
      return {
        stateLabel: tx('welcome.metrics.plan.basic.stateLabel', 'Basic plan'),
        title: tx('welcome.metrics.plan.basic.title', 'Upgrade to Premium for benchmark correlation'),
        copy: tx('welcome.metrics.plan.basic.copy', 'Forecast confidence is already live for you. Premium adds benchmark correlation, upside windows, and the full executive conversion driver inside this module.'),
        ctaLabel: tx('welcome.metrics.plan.basic.cta', 'Upgrade to Premium'),
        previewEyebrow: tx('welcome.metrics.plan.basic.eyebrow', 'Premium unlock'),
        inlineCopy: tx('welcome.metrics.plan.basic.inlineCopy', 'Basic already unlocks forecast confidence. Premium unlocks benchmark correlation, upside windows, and the complete executive insight rail.'),
        destinationLabel: tx('welcome.metrics.plan.basic.destinationLabel', 'Destination · Subscription plans'),
        destinationHint: tx('welcome.metrics.plan.basic.destinationHint', 'Opens plans with a Premium recommendation to unlock benchmark correlation and upside windows.'),
        compactTitle: tx('welcome.metrics.plan.basic.compactTitle', 'Upgrade to Premium for benchmark correlation'),
        compactCopy: tx('welcome.metrics.plan.basic.compactCopy', 'Premium adds benchmark correlation, upside windows, and the full executive forecast layer.'),
        compactDestinationHint: tx('welcome.metrics.plan.basic.compactDestinationHint', 'Opens plans with a Premium recommendation.'),
        onPress: () => goToPlanUpgrade('premium', 'Unlock Premium Growth Correlation'),
      };
    }
    return {
      stateLabel: tx('welcome.metrics.plan.premium.stateLabel', 'Premium unlocked'),
      title: tx('welcome.metrics.plan.premium.title', 'Forecast and benchmark correlation are fully unlocked'),
      copy: tx('welcome.metrics.plan.premium.copy', 'You already have the complete insight surface: forecast confidence, benchmark correlation, and upside windows are all active inside this module.'),
      ctaLabel: tx('welcome.metrics.plan.premium.cta', 'Open dashboard'),
      previewEyebrow: tx('welcome.metrics.plan.premium.eyebrow', 'Premium active'),
      inlineCopy: tx('welcome.metrics.plan.premium.inlineCopy', 'Premium gives you the full growth intelligence surface — no locks, no teaser states, just the complete executive view.'),
      destinationLabel: tx('welcome.metrics.plan.premium.destinationLabel', 'Destination · Dashboard forecast workspace'),
      destinationHint: tx('welcome.metrics.plan.premium.destinationHint', 'Takes you to the live dashboard so you can continue from this benchmark story immediately.'),
      compactTitle: tx('welcome.metrics.plan.premium.compactTitle', 'Open your live forecast workspace'),
      compactCopy: tx('welcome.metrics.plan.premium.compactCopy', 'Premium is fully unlocked. Jump into the live dashboard and continue from this benchmark story.'),
      compactDestinationHint: tx('welcome.metrics.plan.premium.compactDestinationHint', 'Takes you straight to the forecast workspace.'),
      onPress: () => router.push('/dashboard?focus=growth-intelligence' as any),
    };
  }, [goToPlanUpgrade, planState, router, tx]);

  const lockedInsights = useMemo(() => ([
    {
      label: tx('welcome.metrics.insight.forecastConfidence', 'Forecast confidence'),
      value: `${forecastConfidenceValue}%`,
      unlocked: hasBasicPlan,
      unlockLabel: tx('welcome.metrics.unlock.basic', 'Basic'),
      detail: tx('welcome.metrics.insight.forecastConfidenceDetail', 'Live confidence score for the next momentum window.'),
      preview: tx('welcome.metrics.insight.forecastConfidencePreview', 'Basic unlock shows how confidently RealAICoach expects the next lift window to hold.'),
    },
    {
      label: tx('welcome.metrics.insight.benchmarkCorrelation', 'Benchmark correlation'),
      value: `${benchmarkCorrelationValue} r`,
      unlocked: hasPremiumPlan,
      unlockLabel: tx('welcome.metrics.unlock.premium', 'Premium'),
      detail: tx('welcome.metrics.insight.benchmarkCorrelationDetail', 'Correlation between coaching momentum and the benchmark line.'),
      preview: tx('welcome.metrics.insight.benchmarkCorrelationPreview', 'Premium reveals how closely your momentum tracks the benchmark efficiency curve.'),
    },
    {
      label: tx('welcome.metrics.insight.upsideWindow', 'Upside window'),
      value: `+${upsideWindowValue}%`,
      unlocked: hasPremiumPlan,
      unlockLabel: tx('welcome.metrics.unlock.premium', 'Premium'),
      detail: tx('welcome.metrics.insight.upsideWindowDetail', 'Projected efficiency upside if the current lift window continues.'),
      preview: tx('welcome.metrics.insight.upsideWindowPreview', 'Premium unlocks the next 30-day upside window and the conversion case behind it.'),
    },
  ]), [benchmarkCorrelationValue, forecastConfidenceValue, hasBasicPlan, hasPremiumPlan, tx, upsideWindowValue]);

  const METRICS = useMemo(() => {
    const proofPoints = growthIntelligence?.proof_points || [];
    const toneMap: Record<string, string> = {
      accent: WC.accent,
      indigo: WC.indigoText,
      warning: WC.warningText,
      success: WC.successText,
    };
    return proofPoints.map((item, idx) => ({
      icon: idx === 0 ? 'pulse' : idx === 1 ? 'people' : idx === 2 ? 'flash' : 'globe',
      label: item.label,
      raw: item.value,
      fmt: item.value >= 1000 ? 'k' as const : 'number' as const,
      color: toneMap[item.tone] || WC.accent,
      desc: idx === 0
        ? growthIntelligence?.current_momentum_label || tx('welcome.metrics.proof.currentMomentum', 'Live momentum rising')
        : idx === 1
          ? tx('welcome.metrics.proof.enterpriseAdoption', 'Enterprise adoption depth')
          : idx === 2
            ? tx('welcome.metrics.proof.workflowThroughput', 'Workflow throughput today')
            : tx('welcome.metrics.proof.globalIntelligence', 'Global coach intelligence network'),
    }));
  }, [growthIntelligence, WC.accent, WC.indigoText, WC.warningText, WC.successText, tx]);
  const primaryMetrics = isCompactGrowthLayout ? METRICS.slice(0, 2) : METRICS;
  const secondaryMetrics = isCompactGrowthLayout ? METRICS.slice(2) : [];
  const showInsightRail = !isCompactGrowthLayout;
  const showPremiumTeaser = !isCompactGrowthLayout;
  const showCompactMetricStack = !isPhoneLayout;
  const compactLockedInsights = isPhoneLayout ? lockedInsights.slice(0, 1) : lockedInsights.slice(0, 2);

  const milestonePoints = chartData.filter((point: GrowthIntelligencePoint) => point?.milestone?.title).slice(0, 3);

  const chartTheme = useMemo(() => ({
    text: WC.text,
    textSec: WC.textSec,
    textMuted: WC.textMuted,
    border: withAlpha(WC.border, isDark ? '99' : '14'),
    borderStrong: withAlpha(WC.accent, isDark ? '38' : '2E'),
    tooltipBg: withAlpha(WC.surfaceElevated || WC.card, isDark ? 'F5' : 'FF'),
    accent: WC.accentText || WC.accent,
    grid: withAlpha(WC.border, isDark ? '4D' : '14'),
    shadow: withAlpha(WC.shadowColor, isDark ? 'B8' : '1A'),
    areaStroke: WC.accent,
    areaFillStart: withAlpha(WC.accent, isDark ? '57' : '3D'),
    areaFillEnd: withAlpha(WC.accent, '05'),
    benchmark: WC.warningText,
  }), [WC, isDark]);

  const ChartLib = Recharts && Platform.OS === 'web' ? Recharts : null;
  const chartHeight = isDesktop ? 300 : isPhoneLayout ? 180 : 220;
  const shouldUseCompactTooltip = isPhoneLayout;
  const showInteractiveTooltip = !isPhoneLayout;
  const yAxisWidth = isPhoneLayout ? 0 : 44;
  const chartMargin = useMemo(() => {
    if (isPhoneLayout) {
      return { top: 6, right: 2, left: 2, bottom: 0 };
    }
    if (isCompactGrowthLayout) {
      return { top: 8, right: 6, left: -8, bottom: 0 };
    }
    return { top: 10, right: 10, left: -18, bottom: 0 };
  }, [isCompactGrowthLayout, isPhoneLayout]);

  return (
    <Animated.View
      style={[styles.wrap, { opacity: fadeA, transform: [{ translateY: slideA }] }]}
      data-testid="welcome-metrics"
      testID="welcome-metrics"
    >
      <View style={styles.introCard} data-testid="welcome-metrics-intro-card" testID="welcome-metrics-intro-card">
        <Text style={styles.label}>{t('welcome.metrics.label')}</Text>
        <Text style={[styles.title, isDesktop && { fontSize: 36 }]} data-testid="welcome-metrics-title" testID="welcome-metrics-title">
          {t('welcome.metrics.title')}
        </Text>
        <Text style={styles.sub}>{t('welcome.metrics.subtitle')}</Text>
        <Text style={styles.assurance} data-testid="welcome-metrics-assurance-text" testID="welcome-metrics-assurance-text">
          {t('welcome.metrics.assurance')}
        </Text>
      </View>

      <View style={[styles.moduleCard]} data-testid="growth-chart-module" testID="growth-chart-module">
        <View style={styles.moduleGlowLine} />
        <View style={[styles.moduleGrid, useSplitGrowthLayout && styles.moduleGridDesktop]}>
          <View style={styles.storyPanel}>
            <View style={styles.storyLabelRow}>
              <Text style={styles.storyOverline}>{tx('welcome.metrics.livePerformanceIntelligence', 'Live Performance Intelligence')}</Text>
              <View style={styles.liveDotWrap} data-testid="growth-chart-live-pill" testID="growth-chart-live-pill">
                <View style={styles.liveDot} />
                <Text style={styles.liveDotText}>{tx('welcome.metrics.liveBadge', 'Live')}</Text>
              </View>
            </View>

            <Text style={[styles.storyHeadline, isCompactGrowthLayout && styles.storyHeadlineCompact]} data-testid="growth-chart-headline-value" testID="growth-chart-headline-value">
              +{headlineValue}%
            </Text>
            <Text style={styles.storyMetricLabel} data-testid="growth-chart-headline-label" testID="growth-chart-headline-label">
              {growthIntelligence?.headline_metric?.label || tx('welcome.metrics.headlineMetricLabel', 'Growth efficiency')}
            </Text>

            <View style={styles.premiumBadge} data-testid="performance-badge" testID="performance-badge">
              <Ionicons name="sparkles" size={14} color={chartTheme.accent} />
              <Text style={styles.premiumBadgeText}>{tx('welcome.metrics.deltaVsBaseline', '+{value}% vs baseline').replace('{value}', String(deltaVsBaseline))}</Text>
            </View>

            <Text style={styles.storyCopy} data-testid="growth-chart-narrative" testID="growth-chart-narrative">
              {growthIntelligence?.narrative_summary || tx('welcome.metrics.narrativeFallback', 'Teams using RealAICoach sustain measurable improvement across adoption, output velocity, and coaching completion.')}
            </Text>

            <View style={styles.confidenceCard} data-testid="growth-chart-confidence-card" testID="growth-chart-confidence-card">
              <View style={styles.confidenceHeaderRow}>
              <Text style={styles.confidenceLabel}>{tx('welcome.metrics.confidence', 'Confidence')}</Text>
                <Text style={styles.confidenceValue}>{confidenceScore}%</Text>
              </View>
              <Text style={styles.confidenceText}>{growthIntelligence?.confidence?.label || tx('welcome.metrics.confidenceLabelFallback', 'Validated across live coaching workflows')}</Text>
              <Text style={styles.confidenceBenchmarkStory} data-testid="growth-benchmark-personalized-story" testID="growth-benchmark-personalized-story">{benchmarkStoryText}</Text>
            </View>

            <View style={styles.proofGrid} data-testid="growth-chart-proof-grid" testID="growth-chart-proof-grid">
              {primaryMetrics.map((m, i) => (
                <View key={i} style={styles.proofCard} data-testid={`growth-chart-proof-card-${i}`} testID={`growth-chart-proof-card-${i}`}>
                  <View style={[styles.proofIcon, { backgroundColor: `${m.color}18`, borderColor: `${m.color}28` }]}>
                    <Ionicons name={m.icon as any} size={14} color={m.color} />
                  </View>
                  <View style={{ flex: 1, alignItems: isPhoneLayout ? 'center' : 'flex-start' }}>
                    <AnimatedCounter value={m.raw} format={m.fmt} style={[styles.proofValue, { color: m.color }]} />
                    <Text style={styles.proofLabel}>{m.label}</Text>
                    <Text style={styles.proofDesc}>{m.desc}</Text>
                  </View>
                </View>
              ))}
            </View>

            {secondaryMetrics.length > 0 && showCompactMetricStack ? (
              <View style={styles.secondaryMetricRow} data-testid="growth-chart-secondary-metrics" testID="growth-chart-secondary-metrics">
                {secondaryMetrics.map((metric, idx) => (
                  <View key={`${metric.label}-${idx}`} style={styles.secondaryMetricChip} data-testid={`growth-chart-secondary-metric-${idx}`} testID={`growth-chart-secondary-metric-${idx}`}>
                    <Text style={styles.secondaryMetricValue}>{formatCompact(metric.raw)}</Text>
                    <Text style={styles.secondaryMetricLabel}>{metric.label}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {showInsightRail ? (
              <View style={styles.insightRail} data-testid="growth-chart-insight-rail" testID="growth-chart-insight-rail">
                <View style={styles.insightChip}>
                  <Text style={styles.insightChipLabel}>{tx('welcome.metrics.bestPeriod', 'Best period')}</Text>
                  <Text style={styles.insightChipValue}>{strongestPeriodLabel}</Text>
                </View>
                <View style={styles.insightChip}>
                  <Text style={styles.insightChipLabel}>{tx('welcome.metrics.watchpoint', 'Watchpoint')}</Text>
                  <Text style={styles.insightChipValue}>{weakestPeriodLabel}</Text>
                </View>
              </View>
            ) : null}

            {showPremiumTeaser ? (
              <View style={styles.premiumTeaserCard} data-testid="growth-chart-premium-teaser" testID="growth-chart-premium-teaser">
                <Ionicons name={planState === 'premium' ? 'sparkles' : 'lock-closed'} size={14} color={planState === 'premium' ? WC.accent : WC.warningText} />
                <Text style={styles.premiumTeaserText}>{conversionStrip.inlineCopy}</Text>
              </View>
            ) : null}
          </View>

          <View style={styles.chartPanel} data-testid="welcome-metrics-chart" testID="welcome-metrics-chart">
            <View style={styles.chartHeader}>
              <View style={{ alignItems: isPhoneLayout ? 'center' : 'flex-start' }}>
                <Text style={styles.chartTitle}>{t('welcome.metrics.growthTrajectory')}</Text>
                <Text style={styles.chartSubtitle}>{comparisonLabel}</Text>
              </View>
              <View style={styles.rangeToggleWrap} data-testid="growth-chart-range-toggle" testID="growth-chart-range-toggle">
                {RANGE_OPTIONS.map((option) => {
                  const active = selectedRange === option.id;
                  return (
                    <TouchableOpacity
                      key={option.id}
                      onPress={() => setSelectedRange(option.id)}
                      style={[styles.rangeToggleButton, active && styles.rangeToggleButtonActive]}
                      data-testid={`growth-chart-range-${option.id}`}
                      testID={`growth-chart-range-${option.id}`}
                    >
                      <Text style={[styles.rangeToggleText, active && styles.rangeToggleTextActive]}>{option.label}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>

            {ChartLib && chartData.length > 0 ? (
              <View style={styles.chartCanvasWrap} data-testid="growth-chart-canvas" testID="growth-chart-canvas">
                <ChartLib.ResponsiveContainer width="100%" height={chartHeight}>
                  <ChartLib.AreaChart data={chartData} margin={chartMargin}>
                    <defs>
                      <linearGradient id="welcomeGrowthGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={chartTheme.areaFillStart} stopOpacity={1} />
                        <stop offset="95%" stopColor={chartTheme.areaFillEnd} stopOpacity={1} />
                      </linearGradient>
                    </defs>
                    <ChartLib.CartesianGrid strokeDasharray="3 3" stroke={chartTheme.grid} vertical={false} />
                    <ChartLib.XAxis dataKey="label" tick={{ fill: chartTheme.textMuted, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <ChartLib.YAxis hide={isPhoneLayout} tick={{ fill: chartTheme.textMuted, fontSize: 11 }} axisLine={false} tickLine={false} width={yAxisWidth} domain={[0, 100]} />
                    {showInteractiveTooltip ? (
                      <ChartLib.Tooltip content={<ChartTooltip theme={chartTheme} comparisonLabel={comparisonLabel} compact={shouldUseCompactTooltip} />} cursor={{ stroke: chartTheme.borderStrong, strokeDasharray: '4 4' }} />
                    ) : null}
                    <ChartLib.Area type="monotone" dataKey="benchmark_score" stroke={chartTheme.benchmark} fill="transparent" strokeWidth={1.8} strokeDasharray="6 6" dot={false} activeDot={{ r: 4, fill: chartTheme.benchmark, stroke: chartTheme.tooltipBg, strokeWidth: 2 }} />
                    <ChartLib.Area type="monotone" dataKey="growth_score" stroke={chartTheme.areaStroke} fill="url(#welcomeGrowthGradient)" strokeWidth={2.6} dot={{ r: 3.5, fill: chartTheme.areaStroke, stroke: chartTheme.tooltipBg, strokeWidth: 2 }} activeDot={{ r: 6, fill: chartTheme.areaStroke, stroke: chartTheme.tooltipBg, strokeWidth: 2.5 }} animationDuration={900} />
                  </ChartLib.AreaChart>
                </ChartLib.ResponsiveContainer>
              </View>
            ) : (
              <EmptySparkline
                styles={styles}
                theme={WC}
                title={tx('welcome.metrics.empty.title', 'Growth intelligence is syncing')}
                subtitle={tx('welcome.metrics.empty.subtitle', 'RealAICoach will render benchmarked trend intelligence as soon as the latest telemetry snapshot is available.')}
              />
            )}

            <View style={styles.chartLegendRow} data-testid="growth-chart-legend" testID="growth-chart-legend">
              <View style={styles.chartLegendItem}>
                <View style={[styles.chartLegendSwatch, { backgroundColor: chartTheme.areaStroke }]} />
                <Text style={styles.chartLegendText}>{tx('welcome.metrics.legend.realAICoachMomentum', 'RealAICoach momentum')}</Text>
              </View>
              <View style={styles.chartLegendItem}>
                <View style={[styles.chartLegendSwatch, { backgroundColor: chartTheme.benchmark }]} />
                <Text style={styles.chartLegendText}>{comparisonLabel}</Text>
              </View>
            </View>

            {!isCompactGrowthLayout ? (
              <View style={styles.chartLowerStack}>
                <View style={styles.milestoneRail} data-testid="growth-chart-milestone-rail" testID="growth-chart-milestone-rail">
                  {milestonePoints.length === 0 ? (
                    <View style={styles.milestoneCardMuted} data-testid="growth-chart-milestone-empty" testID="growth-chart-milestone-empty">
                      <Text style={styles.milestoneTag}>{tx('welcome.metrics.liveInsight', 'Live insight')}</Text>
                      <Text style={styles.milestoneTitle}>{tx('welcome.metrics.milestoneEmpty', 'Milestones will populate as the active time range updates.')}</Text>
                    </View>
                  ) : milestonePoints.map((point, idx) => (
                    <View key={`${point.period_start}-${idx}`} style={styles.milestoneCard} data-testid={`growth-chart-milestone-${idx}`} testID={`growth-chart-milestone-${idx}`}>
                      <Text style={styles.milestoneTag}>{point.label}</Text>
                      <Text style={styles.milestoneTitle}>{point.milestone?.title}</Text>
                      <Text style={styles.milestoneImpact}>{point.milestone?.impact_label}</Text>
                    </View>
                  ))}
                </View>

                <View style={styles.forecastCard} data-testid="growth-chart-forecast-card" testID="growth-chart-forecast-card">
                  <Ionicons name="trending-up-outline" size={16} color={WC.accent} />
                  <Text style={styles.forecastText}>{activeRange?.forecast_teaser || tx('welcome.metrics.forecastFallback', 'Maintain the current rhythm to unlock another measurable efficiency lift.')}</Text>
                </View>
              </View>
            ) : (
              <View style={styles.compactLowerStack}>
                <View style={styles.compactSignalRow} data-testid="growth-chart-milestone-rail" testID="growth-chart-milestone-rail">
                  <View style={styles.compactSignalChip}>
                    <Text style={styles.compactSignalLabel}>{tx('welcome.metrics.bestPeriod', 'Best period')}</Text>
                    <Text style={styles.compactSignalValue}>{strongestPeriodLabel}</Text>
                  </View>
                  <View style={styles.milestoneCardMuted} data-testid="growth-chart-milestone-empty" testID="growth-chart-milestone-empty">
                    <Text style={styles.milestoneTag}>{tx('welcome.metrics.signal', 'Signal')}</Text>
                    <Text style={styles.milestoneTitle}>{milestonePoints[0]?.milestone?.title || tx('welcome.metrics.signalFallback', 'Live benchmark shifts update with the selected range.')}</Text>
                  </View>
                </View>

                <View style={styles.forecastCard} data-testid="growth-chart-forecast-card" testID="growth-chart-forecast-card">
                  <Ionicons name="trending-up-outline" size={16} color={WC.accent} />
                  <Text style={styles.forecastText}>{activeRange?.forecast_teaser || tx('welcome.metrics.forecastFallback', 'Maintain the current rhythm to unlock another measurable efficiency lift.')}</Text>
                </View>
              </View>
            )}
          </View>
        </View>

        <View style={[styles.planAwareStrip, isCompactGrowthLayout && styles.planAwareStripCompact]} data-testid="growth-plan-upgrade-strip" testID="growth-plan-upgrade-strip">
          <View style={styles.planAwareHeaderRow}>
              <View style={styles.planAwareCopyCol}>
              <Text style={styles.planAwareEyebrow}>{conversionStrip.previewEyebrow}</Text>
              <View style={styles.planAwareTitleRow}>
                <View style={styles.planAwareStatePill} data-testid="growth-plan-state-pill" testID="growth-plan-state-pill">
                  <Text style={styles.planAwareStateText}>{conversionStrip.stateLabel}</Text>
                </View>
              </View>
              <Text style={[styles.planAwareTitle, isCompactGrowthLayout && styles.planAwareTitleCompact]} data-testid="growth-plan-upgrade-strip-title" testID="growth-plan-upgrade-strip-title">{isCompactGrowthLayout ? conversionStrip.compactTitle : conversionStrip.title}</Text>
              <Text style={styles.planAwareCopy}>{isCompactGrowthLayout ? conversionStrip.compactCopy : conversionStrip.copy}</Text>
              <View style={styles.planAwareDestinationChip} data-testid="growth-plan-destination-chip" testID="growth-plan-destination-chip">
                <Text style={styles.planAwareDestinationLabel}>{conversionStrip.destinationLabel}</Text>
                <Text style={styles.planAwareDestinationHint}>{isCompactGrowthLayout ? conversionStrip.compactDestinationHint : conversionStrip.destinationHint}</Text>
              </View>
            </View>

            <TouchableOpacity onPress={conversionStrip.onPress} style={[styles.planAwareCtaButton, planState === 'premium' && styles.planAwareCtaButtonPremium]} data-testid="growth-plan-cta-button" testID="growth-plan-cta-button">
              <Text style={[styles.planAwareCtaText, planState === 'premium' && styles.planAwareCtaTextPremium]}>{conversionStrip.ctaLabel}</Text>
              <Ionicons name={planState === 'premium' ? 'arrow-forward-circle' : 'diamond-outline'} size={16} color={planState === 'premium' ? WC.text : WC.bg} />
            </TouchableOpacity>
          </View>

          <View style={styles.planAwareInsightsGrid} data-testid="growth-plan-insights-grid" testID="growth-plan-insights-grid">
            {(isCompactGrowthLayout ? compactLockedInsights : lockedInsights).map((insight, idx) => (
              <View key={`${insight.label}-${idx}`} style={[styles.planAwareInsightCard, !insight.unlocked && styles.planAwareInsightCardLocked]} data-testid={`growth-plan-insight-card-${idx}`} testID={`growth-plan-insight-card-${idx}`}>
                <View style={styles.planAwareInsightHeader}>
                  <Text style={styles.planAwareInsightLabel}>{insight.label}</Text>
                  <View style={[styles.planAwareInsightPill, insight.unlocked ? styles.planAwareInsightPillUnlocked : styles.planAwareInsightPillLocked]} data-testid={`growth-plan-insight-card-${idx}-${insight.unlocked ? 'unlocked' : 'locked'}`} testID={`growth-plan-insight-card-${idx}-${insight.unlocked ? 'unlocked' : 'locked'}`}>
                    <Ionicons name={insight.unlocked ? 'checkmark-circle' : 'lock-closed'} size={11} color={insight.unlocked ? WC.successText : WC.warningText} />
                    <Text style={[styles.planAwareInsightPillText, insight.unlocked ? styles.planAwareInsightPillTextUnlocked : styles.planAwareInsightPillTextLocked]}>{insight.unlocked ? tx('welcome.metrics.unlocked', 'Unlocked') : insight.unlockLabel}</Text>
                  </View>
                </View>
                <Text style={[styles.planAwareInsightValue, !insight.unlocked && styles.planAwareInsightValueLocked]}>{insight.unlocked ? insight.value : '•••'}</Text>
                <Text style={styles.planAwareInsightMeta}>{insight.unlocked ? insight.detail : insight.preview}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>
    </Animated.View>
  );
}

const cardBlur = Platform.OS === 'web' ? { backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' } as any : {};

function makeStyles(WC: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens, width: number, isDesktop: boolean, useSplitGrowthLayout: boolean) {
  const narrow = width < 560;
  const headingFont = Platform.OS === 'web' ? { fontFamily: 'Outfit, sans-serif' as any } : null;
  const bodyFont = Platform.OS === 'web' ? { fontFamily: 'IBM Plex Sans, sans-serif' as any } : null;
  return StyleSheet.create({
    wrap: {
      paddingHorizontal: horizontalPadding,
      paddingVertical: 80,
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      width: '100%',
      ...(Platform.OS === 'web' ? { marginLeft: 'auto', marginRight: 'auto' } as any : {}),
    },
    introCard: {
      width: '100%',
      maxWidth: 960,
      alignSelf: 'center',
      marginBottom: 34,
      paddingHorizontal: 24,
      paddingVertical: 24,
      borderRadius: 24,
      backgroundColor: WC.glassSurface,
      borderWidth: 1,
      borderColor: WC.glassBorder,
      ...cardBlur,
      ...getShadow('md', isDark),
    },
    label: { color: WC.accent, fontSize: 11, fontWeight: '800', letterSpacing: 2.5, textAlign: 'center', marginBottom: 14, ...(bodyFont || {}) },
    title: { color: WC.text, fontSize: 30, fontWeight: '900', textAlign: 'center', letterSpacing: -0.8, marginBottom: 14, ...(headingFont || {}) },
    sub: { color: WC.textSec, fontSize: 16, textAlign: 'center', lineHeight: 26, maxWidth: 960, alignSelf: 'center', marginBottom: 12, ...(bodyFont || {}) },
    assurance: { color: WC.textMuted, fontSize: 13, textAlign: 'center', lineHeight: 22, maxWidth: 960, alignSelf: 'center', ...(bodyFont || {}) },
    moduleCard: {
      position: 'relative',
      backgroundColor: withAlpha(WC.surface, isDark ? 'F2' : 'FC'),
      borderRadius: 28,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '99' : '14'),
      padding: narrow ? 18 : isDesktop ? 28 : 22,
      overflow: 'hidden',
      ...cardBlur,
      ...getShadow('md', isDark),
    },
    moduleGlowLine: {
      position: 'absolute',
      top: 0,
      left: '5%',
      right: '5%',
      height: 1,
      backgroundColor: withAlpha(WC.accent, isDark ? '52' : '2E'),
    },
    moduleGrid: { gap: 20, flexDirection: 'column', flexWrap: 'nowrap' },
    moduleGridDesktop: { flexDirection: 'row', flexWrap: 'nowrap', alignItems: 'flex-start' },
    storyPanel: {
      flex: useSplitGrowthLayout ? 1 : undefined,
      width: useSplitGrowthLayout ? undefined : '100%',
      flexBasis: 'auto',
      gap: 14,
      minWidth: 0,
      alignSelf: useSplitGrowthLayout ? 'stretch' : 'auto',
    },
    storyLabelRow: { flexDirection: narrow ? 'column' : 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
    storyOverline: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 2.6, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    liveDotWrap: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: withAlpha(WC.surface, isDark ? 'A3' : 'F4'), borderWidth: 1, borderColor: withAlpha(WC.border, isDark ? '99' : '14') },
    liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: WC.success },
    liveDotText: { color: WC.textSec, fontSize: 11, fontWeight: '700', ...(bodyFont || {}) },
    storyHeadline: { color: WC.text, fontSize: narrow ? 42 : 58, lineHeight: narrow ? 44 : 58, fontWeight: '900', letterSpacing: -1.8, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    storyHeadlineCompact: { fontSize: narrow ? 36 : 46, lineHeight: narrow ? 38 : 48 },
    storyMetricLabel: { color: WC.textSec, fontSize: 16, fontWeight: '700', marginTop: -6, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    premiumBadge: {
      alignSelf: narrow ? 'center' : 'flex-start',
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: 999,
      backgroundColor: withAlpha(WC.surface, isDark ? 'B0' : 'F5'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '99' : '14'),
    },
    premiumBadgeText: { color: WC.text, fontSize: 12, fontWeight: '700', ...(bodyFont || {}) },
    storyCopy: { color: WC.textSec, fontSize: 15, lineHeight: 24, maxWidth: 520, textAlign: narrow ? 'center' : 'left', alignSelf: narrow ? 'center' : 'auto', ...(bodyFont || {}) },
    confidenceCard: {
      padding: 16,
      borderRadius: 18,
      backgroundColor: withAlpha(WC.card, isDark ? 'D9' : 'FF'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '80' : '12'),
      alignItems: narrow ? 'center' : 'stretch',
    },
    confidenceHeaderRow: { flexDirection: narrow ? 'column' : 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6, gap: narrow ? 4 : 0 },
    confidenceLabel: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1.6, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    confidenceValue: { color: WC.accent, fontSize: 18, fontWeight: '800', textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    confidenceText: { color: WC.textSec, fontSize: 13, lineHeight: 20, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    confidenceBenchmarkStory: { color: WC.textMuted, fontSize: 12, lineHeight: 18, marginTop: 8, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    proofGrid: { gap: 10 },
    proofCard: {
      flexDirection: narrow ? 'column' : 'row',
      alignItems: 'center',
      gap: 12,
      padding: 14,
      borderRadius: 16,
      backgroundColor: withAlpha(WC.card, isDark ? 'D9' : 'FF'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
    },
    proofIcon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
    proofValue: { fontSize: 22, fontWeight: '800', letterSpacing: -0.6, ...(headingFont || {}) },
    proofLabel: { color: WC.text, fontSize: 13, fontWeight: '700', marginTop: 2, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    proofDesc: { color: WC.textMuted, fontSize: 11, marginTop: 2, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    secondaryMetricRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
    secondaryMetricChip: {
      flex: 1,
      minWidth: 120,
      borderRadius: 14,
      paddingHorizontal: 12,
      paddingVertical: 10,
      backgroundColor: isDark ? withAlpha(WC.card, '0F') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '66' : '0D'),
      alignItems: narrow ? 'center' : 'flex-start',
    },
    secondaryMetricValue: { color: WC.text, fontSize: 14, fontWeight: '800', textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    secondaryMetricLabel: { color: WC.textMuted, fontSize: 10, marginTop: 4, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    insightRail: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
    insightChip: {
      flex: narrow ? undefined : 1,
      minWidth: narrow ? '100%' as any : 0,
      borderRadius: 16,
      padding: 14,
      backgroundColor: withAlpha(WC.card, isDark ? 'D9' : 'FF'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
      alignItems: narrow ? 'center' : 'flex-start',
    },
    insightChipLabel: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    insightChipValue: { color: WC.text, fontSize: 15, fontWeight: '800', marginTop: 6, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    premiumTeaserCard: {
      flexDirection: narrow ? 'column' : 'row',
      gap: 10,
      alignItems: 'center',
      padding: 14,
      borderRadius: 16,
      backgroundColor: withAlpha(WC.warningText, '14'),
      borderWidth: 1,
      borderColor: withAlpha(WC.warningText, isDark ? '2E' : '29'),
    },
    premiumTeaserText: { color: WC.textSec, fontSize: 12, lineHeight: 19, flex: narrow ? undefined : 1, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareStrip: {
      marginTop: 18,
      borderRadius: 22,
      padding: narrow ? 16 : 18,
      backgroundColor: withAlpha(WC.card, isDark ? 'D9' : 'FF'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '99' : '14'),
      gap: 16,
    },
    planAwareStripCompact: { gap: 12 },
    planAwareHeaderRow: {
      flexDirection: useSplitGrowthLayout ? 'row' : 'column',
      alignItems: useSplitGrowthLayout ? 'center' : narrow ? 'center' : 'flex-start',
      justifyContent: 'space-between',
      gap: 14,
    },
    planAwareCopyCol: { flex: 1, gap: 8, minWidth: 0, alignItems: narrow ? 'center' : 'flex-start' },
    planAwareEyebrow: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 2.2, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', justifyContent: narrow ? 'center' : 'flex-start' },
    planAwareStatePill: {
      borderRadius: 999,
      paddingHorizontal: 10,
      paddingVertical: 6,
      borderWidth: 1,
      borderColor: withAlpha(WC.accent, isDark ? '2E' : '29'),
      backgroundColor: withAlpha(WC.accent, isDark ? '1A' : '14'),
    },
    planAwareStateText: { color: WC.accent, fontSize: 11, fontWeight: '800', ...(bodyFont || {}) },
    planAwareTitle: { color: WC.text, fontSize: 22, fontWeight: '800', letterSpacing: -0.5, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    planAwareTitleCompact: { fontSize: narrow ? 18 : 20, lineHeight: narrow ? 24 : 26 },
    planAwareCopy: { color: WC.textSec, fontSize: 13, lineHeight: 21, maxWidth: 720, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareDestinationChip: {
      marginTop: 2,
      borderRadius: 16,
      paddingHorizontal: 12,
      paddingVertical: 10,
      backgroundColor: isDark ? withAlpha(WC.card, '14') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
      gap: 4,
      alignSelf: narrow ? 'center' : 'flex-start',
    },
    planAwareDestinationLabel: { color: WC.text, fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareDestinationHint: { color: WC.textMuted, fontSize: 11, lineHeight: 17, maxWidth: 520, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareCtaButton: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 10,
      alignSelf: useSplitGrowthLayout ? 'auto' : 'stretch',
      paddingHorizontal: 18,
      paddingVertical: 14,
      borderRadius: 999,
      backgroundColor: WC.accent,
      minWidth: narrow ? undefined : 224,
    },
    planAwareCtaButtonPremium: {
      backgroundColor: isDark ? withAlpha(WC.card, '1A') : WC.bgSoft,
      borderWidth: 1,
      borderColor: WC.border,
    },
    planAwareCtaText: { color: WC.bg, fontSize: 13, fontWeight: '800', ...(bodyFont || {}) },
    planAwareCtaTextPremium: { color: WC.text },
    planAwareInsightsGrid: {
      flexDirection: useSplitGrowthLayout ? 'row' : 'column',
      gap: 12,
    },
    planAwareInsightCard: {
      flex: 1,
      minWidth: 0,
      borderRadius: 18,
      padding: 14,
      backgroundColor: isDark ? withAlpha(WC.card, '14') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
      gap: 8,
      alignItems: narrow ? 'center' : 'stretch',
    },
    planAwareInsightCardLocked: {
      backgroundColor: isDark ? withAlpha(WC.card, '0F') : WC.bg,
    },
    planAwareInsightHeader: { flexDirection: narrow ? 'column' : 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
    planAwareInsightLabel: { color: WC.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    planAwareInsightPill: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 5,
      borderRadius: 999,
      paddingHorizontal: 8,
      paddingVertical: 5,
      borderWidth: 1,
    },
    planAwareInsightPillUnlocked: {
      backgroundColor: withAlpha(WC.success, isDark ? '1A' : '14'),
      borderColor: withAlpha(WC.success, isDark ? '29' : '24'),
    },
    planAwareInsightPillLocked: {
      backgroundColor: withAlpha(WC.warningText, isDark ? '1A' : '14'),
      borderColor: withAlpha(WC.warningText, isDark ? '29' : '24'),
    },
    planAwareInsightPillText: { fontSize: 10, fontWeight: '800', ...(bodyFont || {}) },
    planAwareInsightPillTextUnlocked: { color: WC.successText },
    planAwareInsightPillTextLocked: { color: WC.warningText },
    planAwareInsightValue: { color: WC.text, fontSize: 26, fontWeight: '800', letterSpacing: -0.8, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    planAwareInsightValueLocked: { color: WC.textMuted },
    planAwareInsightMeta: { color: WC.textSec, fontSize: 12, lineHeight: 19, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    chartPanel: {
      flex: useSplitGrowthLayout ? 1.45 : undefined,
      width: useSplitGrowthLayout ? undefined : '100%',
      flexBasis: 'auto',
      gap: 14,
      minWidth: 0,
      borderRadius: 22,
      backgroundColor: withAlpha(WC.card, isDark ? 'D4' : 'FF'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
      padding: narrow ? 14 : 20,
      alignSelf: useSplitGrowthLayout ? 'stretch' : 'auto',
    },
    chartHeader: { flexDirection: narrow ? 'column' : 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
    chartTitle: { color: WC.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.5, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    chartSubtitle: { color: WC.textMuted, fontSize: 12, marginTop: 4, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    rangeToggleWrap: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: narrow ? 'center' : 'flex-start' },
    rangeToggleButton: {
      paddingHorizontal: 12,
      paddingVertical: 8,
      borderRadius: 999,
      backgroundColor: withAlpha(WC.surface, isDark ? 'A3' : 'F4'),
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '80' : '14'),
    },
    rangeToggleButtonActive: {
      backgroundColor: withAlpha(WC.accent, isDark ? '29' : '1F'),
      borderColor: withAlpha(WC.accent, isDark ? '42' : '2E'),
    },
    rangeToggleText: { color: WC.textSec, fontSize: 11, fontWeight: '700', ...(bodyFont || {}) },
    rangeToggleTextActive: { color: WC.text, fontWeight: '800' },
    chartCanvasWrap: { width: '100%', minHeight: narrow ? 180 : 220 },
    emptyCard: {
      minHeight: 220,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: WC.border,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: 24,
      gap: 8,
      backgroundColor: isDark ? withAlpha(WC.card, '0F') : WC.bgSoft,
    },
    emptyTitle: { color: WC.text, fontSize: 15, fontWeight: '800', ...(headingFont || {}) },
    emptySub: { color: WC.textMuted, fontSize: 12, textAlign: 'center', lineHeight: 20, ...(bodyFont || {}) },
    chartLegendRow: { flexDirection: 'row', gap: narrow ? 10 : 14, flexWrap: 'wrap', justifyContent: narrow ? 'center' : 'flex-start' },
    chartLegendItem: { flexDirection: 'row', alignItems: 'center', gap: 8, maxWidth: narrow ? '100%' as any : undefined },
    chartLegendSwatch: { width: 12, height: 12, borderRadius: 999 },
    chartLegendText: { color: WC.textMuted, fontSize: 11, fontWeight: '700', ...(bodyFont || {}) },
    chartLowerStack: { gap: 14 },
    milestoneRail: { flexDirection: narrow ? 'column' : 'row', gap: 10 },
    milestoneCard: {
      flex: 1,
      minWidth: 0,
      borderRadius: 16,
      padding: 14,
      backgroundColor: isDark ? withAlpha(WC.card, '14') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
    },
    milestoneCardMuted: {
      width: '100%',
      borderRadius: 16,
      padding: 14,
      backgroundColor: isDark ? withAlpha(WC.card, '0F') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '66' : '0D'),
    },
    milestoneTag: { color: WC.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, textTransform: 'uppercase', ...(bodyFont || {}) },
    milestoneTitle: { color: WC.text, fontSize: 13, fontWeight: '800', lineHeight: 18, marginTop: 6, ...(headingFont || {}) },
    milestoneImpact: { color: WC.accent, fontSize: 12, fontWeight: '700', marginTop: 8, ...(bodyFont || {}) },
    compactLowerStack: { gap: 12 },
    compactSignalRow: { gap: 10 },
    compactSignalChip: {
      borderRadius: 16,
      padding: 14,
      backgroundColor: isDark ? withAlpha(WC.card, '14') : WC.bgSoft,
      borderWidth: 1,
      borderColor: withAlpha(WC.border, isDark ? '73' : '10'),
      alignItems: narrow ? 'center' : 'flex-start',
    },
    compactSignalLabel: { color: WC.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.4, textTransform: 'uppercase', textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
    compactSignalValue: { color: WC.text, fontSize: 15, fontWeight: '800', marginTop: 6, textAlign: narrow ? 'center' : 'left', ...(headingFont || {}) },
    forecastCard: {
      flexDirection: narrow ? 'column' : 'row',
      alignItems: 'center',
      gap: 10,
      borderRadius: 16,
      padding: 14,
      backgroundColor: withAlpha(WC.accent, '14'),
      borderWidth: 1,
      borderColor: withAlpha(WC.accent, isDark ? '29' : '24'),
    },
    forecastText: { color: WC.textSec, fontSize: 12, lineHeight: 19, flex: narrow ? undefined : 1, textAlign: narrow ? 'center' : 'left', ...(bodyFont || {}) },
  });
}
