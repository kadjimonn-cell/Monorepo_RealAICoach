import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StatusBar,
  StyleSheet, Platform, Image, NativeSyntheticEvent, NativeScrollEvent,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { getShadow } from '../src/utils/themeShadows';
import { getTestProps } from '../src/utils/testProps';
import { WelcomeHero } from '../src/components/welcome/WelcomeHero';
import { WelcomeHeroSummaryBand } from '../src/components/welcome/WelcomeHeroSummaryBand';
import { WelcomeMetrics } from '../src/components/welcome/WelcomeMetrics';
import { WelcomeBenefits } from '../src/components/welcome/WelcomeBenefits';
import { WelcomeSocial } from '../src/components/welcome/WelcomeSocial';
import { WelcomeCTA } from '../src/components/welcome/WelcomeCTA';
import { WelcomePricing } from '../src/components/welcome/WelcomePricing';
import { WelcomeFAQ } from '../src/components/welcome/WelcomeFAQ';
import { FloatingImageShowcase } from '../src/components/FloatingImageShowcase';
import { ScrollReveal } from '../src/components/ScrollReveal';
import Footer from '../src/components/Footer';
import { useLanguage } from '../src/i18n/LanguageContext';
import { useIsClient } from '../src/hooks/useIsClient';
import { NAV_LINKS } from '../src/config/siteConfig';
import { WelcomeLandingSkeleton, usePageReady } from '../src/components/SkeletonLoaders';
import { useGlobalPlatformState } from '../src/hooks/useGlobalPlatformState';
import { useGLSBreakpoint } from '../src/components/layout/GlobalLayoutSystem';
import type { GLSTokens } from '../src/context/GLSContext';
import GpsLabelBlocker from '../src/components/GpsLabelBlocker';
import { GpsDataStatusCard } from '../src/components/GpsDataStatusCard';
import { SectionProgressRail } from '../src/components/progress/SectionProgressRail';
import { withAlpha } from '../src/utils/colorAlpha';
import { PLATFORM_BRAND } from '../src/utils/brandProtection';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { trackCareersEvent } from '../src/utils/careersTelemetry';
import { getLatestMediaMentions, listPressArticlesByCategory } from '../src/content/pressArticles';
import { buildCanonicalWelcomeFaq, buildCanonicalWelcomeTestimonials } from '../src/content/welcomeTrustContent';
import { resolveVisitorCtaPath } from '../src/utils/visitorCtaPolicy';
import { GLOBAL_PRICING_POLICY } from '../src/config/pricingPolicy';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import {
  loadWelcomeDecisionPath,
  loadWelcomeSummaryInterest,
  mergeWelcomeDecisionPathSignal,
  persistWelcomeDecisionPath,
  persistWelcomeSummaryInterest,
  type WelcomeDecisionPathMemory,
  type WelcomeSummaryInterestAreaId,
} from '../src/components/welcome/welcomeWorkflowMemory';

const AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY = 'rac:auth-entry-replay-skip-until';
const AUTH_ENTRY_REPLAY_SKIP_WINDOW_MS = 12_000;

function markAuthEntryReplaySkipWindow() {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(
      AUTH_ENTRY_REPLAY_SKIP_UNTIL_KEY,
      String(Date.now() + AUTH_ENTRY_REPLAY_SKIP_WINDOW_MS),
    );
  } catch {
    // no-op
  }
}

const TRUST_COMPANY_FALLBACK = [
  'Apple',
  'FedaPay',
  'Google',
  'Microsoft',
  'Amazon',
  'Meta',
  'Stripe',
  'Salesforce',
  'Shopify',
  'PayPal',
];

const blur = Platform.OS === 'web' ? { backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' } as any : {};

export default function WelcomeScreen() {
  const pageReady = usePageReady();
  const router = useRouter();
  const routeParams = useLocalSearchParams<{
    return_to?: string | string[];
    auth_reason?: string | string[];
    section?: string | string[];
    source?: string | string[];
  }>();
  const { width, isDesktop, padding, tokens } = useGLSBreakpoint();
  const isClient = useIsClient();
  const isWeb = Platform.OS === 'web';
  const isEmbeddedPreview = useMemo(() => {
    if (!(Platform.OS === 'web') || typeof window === 'undefined') return false;
    try {
      return window.self !== window.top;
    } catch {
      return true;
    }
  }, []);
  const [menuOpen, setMenuOpen] = useState(false);
  const { darkMode, themeMode, setThemeMode, colors } = useTheme();
  const { user } = useAuth();
  const { t, languageCode, setLanguage, supportedLanguages } = useLanguage();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const {
    state: gpsState,
    counts,
    loading: gpsLoading,
    error: gpsError,
    refetch: gpsRefetch,
    gpsStatus,
    diagnostics: gpsDiagnostics,
  } = useGlobalPlatformState();
  const isDark = isClient ? darkMode : false;
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [backgroundReady, setBackgroundReady] = useState(false);
  const [deferredSectionsReady, setDeferredSectionsReady] = useState(false);
  const [gpsFallbackActive, setGpsFallbackActive] = useState(false);
  const [gpsFallbackElapsedMs, setGpsFallbackElapsedMs] = useState(0);
  const [activeSection, setActiveSection] = useState('hero');
  const [activeMediaMentionIndex, setActiveMediaMentionIndex] = useState(0);
  const [featuredInPaused, setFeaturedInPaused] = useState(false);
  const ALL_FILTER_VALUE = '__all__';
  const [activeFaqCategory, setActiveFaqCategory] = useState(ALL_FILTER_VALUE);
  const [activeTestimonialSegment, setActiveTestimonialSegment] = useState(ALL_FILTER_VALUE);
  const [hoveredTrustChip, setHoveredTrustChip] = useState('');
  const [pricingSurfaceRequested, setPricingSurfaceRequested] = useState(false);
  const [suppressFloatingChrome, setSuppressFloatingChrome] = useState(false);
  const [rememberedSummaryInterest, setRememberedSummaryInterest] = useState<WelcomeSummaryInterestAreaId | null>(null);
  const [decisionPathMemory, setDecisionPathMemory] = useState<WelcomeDecisionPathMemory | null>(null);
  const LANG_OPTIONS = [
    { code: 'en', label: tx('welcome.language.english', 'English'), flag: 'EN' },
    { code: 'fr', label: tx('welcome.language.french', 'Français'), flag: 'FR' },
    { code: 'es', label: tx('welcome.language.spanish', 'Español'), flag: 'ES' },
    { code: 'de', label: tx('welcome.language.german', 'Deutsch'), flag: 'DE' },
    { code: 'it', label: tx('welcome.language.italian', 'Italiano'), flag: 'IT' },
    { code: 'pt', label: tx('welcome.language.portuguese', 'Português'), flag: 'PT' },
    { code: 'ja', label: tx('welcome.language.japanese', '日本語'), flag: 'JA' },
    { code: 'zh', label: tx('welcome.language.chinese', '中文'), flag: 'ZH' },
    { code: 'hi', label: tx('welcome.language.hindi', 'हिन्दी'), flag: 'HI' },
    { code: 'ar', label: tx('welcome.language.arabic', 'العربية'), flag: 'AR' },
  ];
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionOffsets = useRef<Record<string, number>>({});
  const footerOffsetRef = useRef<number | null>(null);
  const suppressFloatingChromeRef = useRef(false);
  const activeSectionRef = useRef('hero');
  const parallaxY = useRef(0);
  const bgRef = useRef<any>(null);
  const telemetryBootRef = useRef(false);
  const gpsLoadStartedAtRef = useRef<number | null>(null);
  const gpsFallbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const gpsFallbackFiredRef = useRef(false);
  const featuredInMarqueeRef = useRef<ScrollView | null>(null);
  const featuredInOffsetRef = useRef(0);
  const shouldUseFeaturedInAutoMarquee = isDesktop && width >= 1280;
  const shouldRenderWebDesktopBg = isWeb && isClient && isDesktop;
  const shouldRenderWebMobileBg = isWeb && isClient && !isDesktop;
  const shouldRenderNativeBg = !isWeb;
  const trustNames = useMemo(
    () => {
      const gpsNames = Array.isArray(gpsState?.messaging?.trust_names)
        ? gpsState.messaging.trust_names.map((name: any) => String(name || '').trim()).filter(Boolean)
        : [];

      const used = new Set(gpsNames.map((name: string) => name.toLowerCase()));
      const merged = [...gpsNames];
      TRUST_COMPANY_FALLBACK.forEach((name) => {
        const key = name.toLowerCase();
        if (used.has(key)) return;
        merged.push(name);
        used.add(key);
      });

      return merged.slice(0, 12);
    },
    [gpsState?.messaging],
  );

  const latestMediaMentions = useMemo(() => getLatestMediaMentions(6), []);
  const featuredInSources = useMemo(() => {
    const all = listPressArticlesByCategory('All');
    const seen = new Set<string>();
    const entries: { source: string; slug: string; category: string }[] = [];
    all.forEach((item) => {
      const source = String(item.source || '').trim();
      const key = source.toLowerCase();
      if (!source || seen.has(key)) return;
      seen.add(key);
      entries.push({ source, slug: item.slug, category: item.category });
    });
    return entries.slice(0, 9);
  }, []);
  const featuredInMarqueeItems = useMemo(() => [...featuredInSources, ...featuredInSources], [featuredInSources]);
  const coreShellReady = pageReady || isEmbeddedPreview;
  const backgroundLayerReady = backgroundReady || isEmbeddedPreview;
  const sectionsReady = deferredSectionsReady || isEmbeddedPreview;
  const heroAsSeenChipItems = useMemo(() => {
    const limit = isDesktop ? 7 : (width < 430 ? 4 : 5);
    return featuredInSources.slice(0, limit);
  }, [featuredInSources, isDesktop, width]);
  const marqueeProfile = useMemo(() => {
    if (width >= 1180) {
      return { intervalMs: 3200, stepPx: 168, label: 'Desktop slow' };
    }
    if (width >= 768) {
      return { intervalMs: 2500, stepPx: 176, label: 'Tablet medium' };
    }
    return { intervalMs: 1850, stepPx: 182, label: 'Mobile fast' };
  }, [width]);

  const gpsWelcomeTestimonialsCount = useMemo(() => {
    const raw = (gpsState?.messaging as any)?.welcome_testimonials;
    if (!Array.isArray(raw)) return 0;
    return raw.filter((item: any) => String(item?.name || '').trim() && String(item?.quote || item?.text || '').trim()).length;
  }, [gpsState?.messaging]);

  const canonicalWelcomeTestimonials = useMemo(
    () => buildCanonicalWelcomeTestimonials((gpsState?.messaging as any)?.welcome_testimonials, 10),
    [gpsState?.messaging],
  );

  const testimonialSegments = useMemo(() => {
    const unique = Array.from(new Set(canonicalWelcomeTestimonials.map((item) => String(item.segment || 'General').trim()).filter(Boolean)));
    return unique.slice(0, 8);
  }, [canonicalWelcomeTestimonials]);

  const welcomeTestimonialsCount = useMemo(() => canonicalWelcomeTestimonials.length, [canonicalWelcomeTestimonials]);

  const welcomeActivitiesCount = useMemo(() => {
    const raw = (gpsState?.messaging as any)?.welcome_activities;
    if (!Array.isArray(raw)) return 0;
    return raw.filter((item: any) => String(item?.user || '').trim() && String(item?.action || '').trim()).length;
  }, [gpsState?.messaging]);

  const missingWelcomeDataKeys = useMemo(() => {
    const missing: string[] = [];
    if (trustNames.length < 4) missing.push('messaging.trust_names (min 4)');
    if (gpsWelcomeTestimonialsCount < 10) missing.push('messaging.welcome_testimonials (min 10)');
    if (welcomeActivitiesCount < 4) missing.push('messaging.welcome_activities (min 4)');
    return missing;
  }, [trustNames.length, gpsWelcomeTestimonialsCount, welcomeActivitiesCount]);

  const normalizeFaqText = useCallback(
    (value: string) => {
      const featureCount = Number(counts.features || 0);
      if (!value || featureCount <= 0) return value;
      return value.replace(/\b\d+\s+(?=(?:specialized\s+)?(?:AI\s+)?(?:copilots?|features?|tools?))/gi, `${featureCount} `);
    },
    [counts.features],
  );

  const welcomeFaqItems = useMemo(
    () => {
      const canonical = buildCanonicalWelcomeFaq(gpsState?.faq || [], languageCode, 20);
      return canonical.map((item) => ({
        question: normalizeFaqText(item.question),
        answer: normalizeFaqText(item.answer),
        category: item.category,
      }));
    },
    [gpsState?.faq, languageCode, normalizeFaqText],
  );

  const faqCategories = useMemo(() => {
    const unique = Array.from(new Set(welcomeFaqItems.map((item) => String(item.category || 'General').trim()).filter(Boolean)));
    return unique.slice(0, 8);
  }, [welcomeFaqItems]);

  useEffect(() => {
    if (activeFaqCategory !== ALL_FILTER_VALUE && !faqCategories.includes(activeFaqCategory)) {
      setActiveFaqCategory(ALL_FILTER_VALUE);
    }
  }, [ALL_FILTER_VALUE, activeFaqCategory, faqCategories]);

  useEffect(() => {
    if (activeTestimonialSegment !== ALL_FILTER_VALUE && !testimonialSegments.includes(activeTestimonialSegment)) {
      setActiveTestimonialSegment(ALL_FILTER_VALUE);
    }
  }, [ALL_FILTER_VALUE, activeTestimonialSegment, testimonialSegments]);

  const canonicalWelcomePlans = useMemo(
    () => {
      const source = (gpsState?.plans || []).filter((item) => item.status !== 'deprecated');
      if (source.length > 0) {
        return source;
      }
      return [
        {
          plan_id: 'free',
          id: 'free',
          name: t('welcome.pricing.default.free.name', 'Free'),
          description: t('welcome.pricing.default.free.description', 'Core access for getting started.'),
          monthly_price: 0,
          yearly_price: 0,
          features: [
            t('welcome.pricing.default.free.feature1', 'Core AI access'),
            t('welcome.pricing.default.free.feature2', 'Basic dashboard'),
            t('welcome.pricing.default.free.feature3', 'Community support'),
          ],
          limitations: [t('welcome.pricing.default.free.limit1', 'Limited daily usage')],
          status: 'active',
          badge: 'free',
        },
        {
          plan_id: 'basic',
          id: 'basic',
          name: t('welcome.pricing.default.basic.name', 'Basic'),
          description: t('welcome.pricing.default.basic.description', 'For growing users and teams.'),
          monthly_price: GLOBAL_PRICING_POLICY.plans.basic.monthly,
          yearly_price: GLOBAL_PRICING_POLICY.plans.basic.yearly,
          features: [
            t('welcome.pricing.default.basic.feature1', 'Higher daily limits'),
            t('welcome.pricing.default.basic.feature2', 'Standard analytics'),
            t('welcome.pricing.default.basic.feature3', 'Priority queue'),
          ],
          limitations: [t('welcome.pricing.default.basic.limit1', 'No premium-only modules')],
          status: 'active',
          badge: 'basic',
        },
        {
          plan_id: 'premium',
          id: 'premium',
          name: t('welcome.pricing.default.premium.name', 'Premium'),
          description: t('welcome.pricing.default.premium.description', 'Full platform access with advanced governance.'),
          monthly_price: GLOBAL_PRICING_POLICY.plans.premium.monthly,
          yearly_price: GLOBAL_PRICING_POLICY.plans.premium.yearly,
          features: [
            t('welcome.pricing.default.premium.feature1', 'Unlimited daily usage'),
            t('welcome.pricing.default.premium.feature2', 'Advanced analytics'),
            t('welcome.pricing.default.premium.feature3', 'Automation and governance'),
          ],
          limitations: [],
          status: 'active',
          badge: 'premium',
        },
      ];
    },
    [gpsState?.plans, t],
  );

  const updateSuppressFloatingChrome = useCallback((next: boolean) => {
    if (next === suppressFloatingChromeRef.current) return;
    suppressFloatingChromeRef.current = next;
    setSuppressFloatingChrome(next);
  }, []);

  const onScroll = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const y = e.nativeEvent.contentOffset.y;

    if (isWeb && bgRef.current) {
      parallaxY.current = y;
      bgRef.current.style.transform = `translateY(${y * 0.35}px) scale(1.15)`;
    }

    const ordered = Object.entries(sectionOffsets.current)
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

    const viewportHeight = Number(e.nativeEvent.layoutMeasurement?.height || 0);
    const contentHeight = Number(e.nativeEvent.contentSize?.height || 0);
    const footerTop = footerOffsetRef.current;
    const viewportBottom = y + viewportHeight;
    const footerThreshold = isDesktop ? 420 : (width >= 768 ? 420 : 340);
    const contentThreshold = isDesktop ? 620 : (width >= 768 ? 620 : 500);
    const nearFooterByOffset = typeof footerTop === 'number' && viewportBottom >= (footerTop - footerThreshold);
    const nearFooterByContent = viewportHeight > 0 && contentHeight > 0 && viewportBottom >= (contentHeight - contentThreshold);
    const shouldSuppress = Boolean(nearFooterByOffset || nearFooterByContent);

    updateSuppressFloatingChrome(shouldSuppress);
  }, [isDesktop, isWeb, updateSuppressFloatingChrome, width]);

  const C = colors;
  const s = useMemo(() => makeStyles(C, isDark, padding, tokens), [isDark, C, padding, tokens]);
  const viewportChromeWidth = isWeb && isClient && typeof window !== 'undefined' ? window.innerWidth : width;
  const canShowFloatingWelcomeChrome = viewportChromeWidth >= 1680;
  const hideDesktopQuickNavByViewport = width < 1180 || !canShowFloatingWelcomeChrome;
  const showProgressRail = isClient && !suppressFloatingChrome && isDesktop && canShowFloatingWelcomeChrome;
  const useWideTopWelcomeLayout = width >= 1180;
  const compactUtilitySurface = width < 960;
  const phoneUtilitySurface = width < 560;
  const useWideLowerWelcomeLayout = width >= 1180;
  const shouldCenterCareersBanner = true;
  const careersContentMaxWidth = width >= 1680 ? 1120 : width >= 1180 ? 920 : 640;
  const utilityStripSpacing = width >= 1180 ? 12 : 10;
  const lowerWelcomeSpacing = width >= 1180 ? 22 : width >= 768 ? 20 : 16;
  const centeredHeroShellWidth = !useWideTopWelcomeLayout && width >= 900
    ? Math.min(width - (padding * 2), 840)
    : !useWideTopWelcomeLayout && width >= 620
      ? Math.min(width - (padding * 2), 620)
      : undefined;
  const viewerIsAdmin = useMemo(() => hasAdminConsoleVisibility(user as any), [user]);
  const heroSummaryBandTone = useMemo(() => {
    if (viewerIsAdmin && gpsStatus === 'healthy' && !gpsError) return 'live' as const;
    if (viewerIsAdmin && gpsError) return 'degraded' as const;
    if (viewerIsAdmin && gpsStatus === 'loading') return 'syncing' as const;
    return 'public' as const;
  }, [gpsError, gpsStatus, viewerIsAdmin]);

  const welcomeSystemStatusLabel = useMemo(() => {
    if (!viewerIsAdmin) return tx('welcome.systemStatus.static', 'STATIC');
    if (gpsStatus === 'loading') return tx('welcome.systemStatus.syncing', 'SYNCING');
    if (gpsStatus === 'healthy' && !gpsError) return tx('welcome.systemStatus.live', 'LIVE');
    return tx('welcome.systemStatus.degraded', 'DEGRADED');
  }, [gpsError, gpsStatus, tx, viewerIsAdmin]);

  const welcomeSystemStatusColor = useMemo(() => {
    if (!viewerIsAdmin) return C.primary;
    if (gpsStatus === 'loading') return C.primary;
    if (gpsStatus === 'healthy' && !gpsError) return C.success;
    return C.warning;
  }, [C.primary, C.success, C.warning, gpsError, gpsStatus, viewerIsAdmin]);

  const compactFeaturedInItems = useMemo(
    () => featuredInSources.slice(0, phoneUtilitySurface ? 4 : compactUtilitySurface ? 6 : 8),
    [compactUtilitySurface, featuredInSources, phoneUtilitySurface],
  );

  const featuredInCardWidth = useMemo(() => {
    if (width < 560) return '48.2%' as const;
    if (width < 960) return '31.6%' as const;
    return '23.8%' as const;
  }, [width]);

  const featuredInTitleLabel = tx('welcome.featured.title', 'Featured in');
  const featuredInStatusLabel = useMemo(() => {
    if (shouldUseFeaturedInAutoMarquee) {
      return featuredInPaused
        ? tx('welcome.featured.status.autoPaused', 'Paused • synced with newsroom')
        : tx('welcome.featured.status.autoScrolling', 'Auto-scrolling • synced with newsroom');
    }
    if (phoneUtilitySurface) return tx('welcome.featured.status.staticCompact', 'Curated newsroom sources');
    return tx('welcome.featured.status.static', 'Tap any source to open the newsroom');
  }, [featuredInPaused, phoneUtilitySurface, shouldUseFeaturedInAutoMarquee, tx]);

  const mediaMentionsTitleLabel = tx('welcome.media.title', 'Latest media mentions');
  const mediaViewNewsroomLabel = phoneUtilitySurface
    ? tx('welcome.media.viewAllCompact', 'Newsroom')
    : tx('welcome.media.viewAll', 'View newsroom');
  const mediaRotationLabel = phoneUtilitySurface
    ? tx('welcome.media.rotation.compact', 'Updates every few seconds')
    : tx('welcome.media.rotation.default', 'Auto-rotates every few seconds');
  const gpsFallbackCopy = tx('welcome.gps.fallback.copy', 'Loading live platform data is taking longer than expected. Showing stable fallback content.');
  const retryLabel = tx('common.retry', 'Retry');
  const careersEyebrow = tx('welcome.careers.eyebrow', 'Careers at RealAICoach');
  const careersTitle = tx('welcome.careers.title', 'Build the future with an enterprise AI team.');
  const careersCopy = tx('welcome.careers.copy', 'Explore open roles, apply in minutes, and track your application journey end-to-end from one professional careers hub.');
  const careersExploreLabel = tx('welcome.careers.explore', 'Explore Careers');
  const careersTalentLabel = tx('welcome.careers.talentNetwork', 'Join Talent Network');
  const careersTrackLabel = tx('welcome.careers.track', 'Track Application');
  const quickNavigatorLabel = tx('welcome.quickNav.title', 'Quick navigator');
  const quickNavigatorFaqLabel = tx('welcome.quickNav.faq', 'FAQ categories');
  const quickNavigatorTestimonialLabel = tx('welcome.quickNav.testimonials', 'Testimonial segments');
  const quickNavigatorCopy = tx('welcome.quickNav.copy', 'Jump into the highest-signal areas without losing context.');
  const quickNavChipLabel = useCallback((value: string) => {
    const slug = String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
    return slug ? tx(`welcome.quickNav.chip.${slug}`, value) : value;
  }, [tx]);

  const welcomeLastRefreshLabel = useMemo(() => {
    if (!viewerIsAdmin) return tx('welcome.systemStatus.policyBaseline', 'policy baseline');
    const raw = String(gpsDiagnostics?.lastSuccessAt || '').trim();
    if (!raw) return tx('welcome.systemStatus.syncingLower', 'syncing');
    const parsed = Date.parse(raw);
    if (!Number.isFinite(parsed)) return tx('welcome.systemStatus.syncingLower', 'syncing');
    const deltaSec = Math.max(0, Math.floor((Date.now() - parsed) / 1000));
    if (deltaSec < 60) return tx('welcome.media.time.secondsAgo', '{count}s ago').replace('{count}', String(deltaSec));
    const deltaMin = Math.floor(deltaSec / 60);
    if (deltaMin < 60) return tx('welcome.media.time.minutesAgo', '{count}m ago').replace('{count}', String(deltaMin));
    const deltaHours = Math.floor(deltaMin / 60);
    return tx('welcome.media.time.hoursAgo', '{count}h ago').replace('{count}', String(deltaHours));
  }, [gpsDiagnostics?.lastSuccessAt, tx, viewerIsAdmin]);

  const setSectionOffset = useCallback((key: string, y: number) => {
    sectionOffsets.current[key] = y;
  }, []);

  useEffect(() => {
    if (!isWeb || typeof window === 'undefined') return;

    let observer: IntersectionObserver | null = null;
    let frameId: number | null = null;
    let disposed = false;

    const evaluateFromRect = () => {
      const footerEl = document.querySelector('[data-testid="welcome-footer-wrapper"]') as HTMLElement | null;
      if (!footerEl) return;
      const rect = footerEl.getBoundingClientRect();
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const revealOffset = isDesktop ? 200 : (width >= 768 ? 300 : 260);
      const nearFooter = rect.top <= (viewportHeight - revealOffset) && rect.bottom >= 0;
      updateSuppressFloatingChrome(nearFooter);
    };

    const attachObserver = () => {
      if (disposed) return;
      const footerEl = document.querySelector('[data-testid="welcome-footer-wrapper"]') as HTMLElement | null;
      if (!footerEl) {
        frameId = window.requestAnimationFrame(attachObserver);
        return;
      }

      observer = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (!entry) return;
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
        const revealOffset = isDesktop ? 200 : (width >= 768 ? 300 : 260);
        const intersects = entry.isIntersecting && entry.intersectionRatio > 0;
        const nearByTop = entry.boundingClientRect.top <= (viewportHeight - revealOffset);
        updateSuppressFloatingChrome(intersects || nearByTop);
      }, {
        threshold: [0, 0.01, 0.08, 0.2],
      });

      observer.observe(footerEl);
      evaluateFromRect();
    };

    attachObserver();
    window.addEventListener('resize', evaluateFromRect);
    window.addEventListener('scroll', evaluateFromRect, { passive: true });

    return () => {
      disposed = true;
      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }
      if (observer) {
        observer.disconnect();
      }
      window.removeEventListener('resize', evaluateFromRect);
      window.removeEventListener('scroll', evaluateFromRect);
    };
  }, [isDesktop, isWeb, updateSuppressFloatingChrome, width]);

  const emitWelcomeTelemetry = useCallback((phase: string, extra: Record<string, any> = {}) => {
    const payload = {
      phase,
      route: '/welcome',
      ts: new Date().toISOString(),
      ...extra,
    };

    try {
      (globalThis as any).__welcomeReadinessTelemetry = [
        ...(((globalThis as any).__welcomeReadinessTelemetry || []) as any[]).slice(-49),
        payload,
      ];
    } catch (error) { handleAppRecoverableError({ scope: 'welcome.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }

    if (isWeb && typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
      try {
        window.dispatchEvent(new CustomEvent('welcome-readiness', { detail: payload }));
      } catch (error) { handleAppRecoverableError({ scope: 'welcome.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, [isWeb]);

  useEffect(() => {
    return () => {
      if (gpsFallbackTimerRef.current) {
        clearTimeout(gpsFallbackTimerRef.current);
        gpsFallbackTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!pageReady || telemetryBootRef.current) return;
    telemetryBootRef.current = true;
    emitWelcomeTelemetry('route_loaded', {
      theme_mode: themeMode,
      dark_mode: isDark,
    });
  }, [emitWelcomeTelemetry, isDark, pageReady, themeMode]);

  useEffect(() => {
    if (!pageReady) return;

    if (gpsLoading && !gpsError) {
      if (!gpsLoadStartedAtRef.current) {
        gpsLoadStartedAtRef.current = Date.now();
        emitWelcomeTelemetry('gps_loading_started');
      }

      if (!gpsFallbackTimerRef.current) {
        gpsFallbackTimerRef.current = setTimeout(() => {
          gpsFallbackTimerRef.current = null;
          gpsFallbackFiredRef.current = true;
          setGpsFallbackActive(true);
          const elapsed = gpsLoadStartedAtRef.current ? (Date.now() - gpsLoadStartedAtRef.current) : 0;
          setGpsFallbackElapsedMs(elapsed);
          emitWelcomeTelemetry('fallback_rendered', {
            reason: 'gps_loading_timeout',
            elapsed_ms: elapsed,
          });
        }, 3200);
      }
      return;
    }

    if (gpsFallbackTimerRef.current) {
      clearTimeout(gpsFallbackTimerRef.current);
      gpsFallbackTimerRef.current = null;
    }

    if (gpsLoadStartedAtRef.current) {
      const elapsed = Date.now() - gpsLoadStartedAtRef.current;
      setGpsFallbackElapsedMs(elapsed);
      emitWelcomeTelemetry(gpsError ? 'gps_error' : 'gps_ready', {
        elapsed_ms: elapsed,
        fallback_used: gpsFallbackFiredRef.current,
      });
    }

    gpsLoadStartedAtRef.current = null;
    gpsFallbackFiredRef.current = false;
    setGpsFallbackActive(false);
  }, [emitWelcomeTelemetry, gpsError, gpsLoading, pageReady]);

  const applyLanguageSelection = useCallback((langCode: string, closeMenu: boolean) => {
    const next = String(langCode || '').trim().toLowerCase();
    if (!next || next === languageCode) {
      if (closeMenu) setLangMenuOpen(false);
      return;
    }

    if (closeMenu) setLangMenuOpen(false);

    if (isWeb && typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          setLanguage(langCode);
        });
      });
      return;
    }

    setLanguage(langCode);
  }, [isWeb, languageCode, setLanguage]);

  const markSummaryInterest = useCallback((areaId: WelcomeSummaryInterestAreaId) => {
    setRememberedSummaryInterest((prev) => (prev === areaId ? prev : areaId));
    void persistWelcomeSummaryInterest({
      areaId,
      updatedAt: new Date().toISOString(),
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const restoreSummaryInterest = async () => {
      const memory = await loadWelcomeSummaryInterest();
      if (cancelled || !memory) return;
      setRememberedSummaryInterest(memory.areaId);
    };
    void restoreSummaryInterest();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const restoreDecisionPath = async () => {
      const memory = await loadWelcomeDecisionPath();
      if (cancelled || !memory) return;
      setDecisionPathMemory(memory);
    };
    void restoreDecisionPath();
    return () => { cancelled = true; };
  }, []);

  const recordDecisionPathSignal = useCallback((areaId: WelcomeSummaryInterestAreaId, weight = 1) => {
    setDecisionPathMemory((prev) => {
      const next = mergeWelcomeDecisionPathSignal(prev, areaId, weight);
      void persistWelcomeDecisionPath(next);
      return next;
    });
  }, []);

  const scrollToSection = useCallback((section: string): boolean => {
    if (isWeb && typeof document !== 'undefined') {
      const nodes = Array.from(document.querySelectorAll(`[data-testid="welcome-section-${section}"]`)) as HTMLElement[];
      const el = nodes.find((node) => {
        const rect = node.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        const cs = window.getComputedStyle(node);
        if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity || '1') === 0) return false;
        return true;
      }) || nodes[nodes.length - 1] || null;
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return true;
      }
    }

    const y = sectionOffsets.current[section];
    if (typeof y === 'number') {
      scrollRef.current?.scrollTo({ y: Math.max(0, y - 84), animated: true });
      return true;
    }
    return false;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const navigateToSection = useCallback((section: string) => {
    if (section === 'pricing') {
      setPricingSurfaceRequested(true);
    }
    if (section === 'features') {
      markSummaryInterest('features');
      recordDecisionPathSignal('features', 2);
    }
    if (section === 'pricing') {
      markSummaryInterest('pricing');
      recordDecisionPathSignal('pricing', 2);
    }
    if (section === 'social-proof') {
      markSummaryInterest('social-proof');
      recordDecisionPathSignal('social-proof', 2);
    }
    return scrollToSection(section);
  }, [markSummaryInterest, recordDecisionPathSignal, scrollToSection]);

  const getSingleParam = useCallback((value?: string | string[]) => {
    if (Array.isArray(value)) return String(value[0] || '').trim();
    return String(value || '').trim();
  }, []);

  const readUrlSectionIntent = useCallback(() => {
    const routeSection = getSingleParam(routeParams.section);
    if (routeSection) return routeSection;
    if (!isWeb || typeof window === 'undefined') return '';
    const params = new URLSearchParams(window.location.search);
    const sectionFromQuery = String(params.get('section') || '').trim();
    if (sectionFromQuery) return sectionFromQuery;
    return String(window.location.hash || '').replace(/^#/, '').trim();
  }, [getSingleParam, isWeb, routeParams.section]);

  const normalizePricingCompareUrlAfterScroll = useCallback(() => {
    if (!isWeb || typeof window === 'undefined' || typeof window.history === 'undefined') {
      return;
    }
    try {
      const current = new URL(window.location.href);
      const section = String(current.searchParams.get('section') || '').trim();
      const source = String(current.searchParams.get('source') || '').trim();
      if (section !== 'pricing' || source !== 'pricing-compare') {
        return;
      }

      current.searchParams.delete('section');
      current.searchParams.delete('source');

      const nextSearch = current.searchParams.toString();
      const nextUrl = `${current.pathname}${nextSearch ? `?${nextSearch}` : ''}${current.hash || ''}`;
      const activeUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (nextUrl !== activeUrl) {
        window.history.replaceState(window.history.state, '', nextUrl);
      }
    } catch {
      // no-op on malformed URL state
    }
  }, [isWeb]);

  const buildAuthEntryPath = useCallback((basePath: '/auth/login' | '/auth/register') => {
    const returnTo = getSingleParam(routeParams.return_to);
    const authReason = getSingleParam(routeParams.auth_reason);
    const qs = new URLSearchParams();
    if (returnTo && returnTo.startsWith('/')) {
      qs.set('return_to', returnTo);
    }
    if (authReason) {
      qs.set('auth_reason', authReason);
    }
    const query = qs.toString();
    return query ? `${basePath}?${query}` : basePath;
  }, [getSingleParam, routeParams.auth_reason, routeParams.return_to]);

  const goLogin = () => {
    markAuthEntryReplaySkipWindow();
    const target = resolveVisitorCtaPath(buildAuthEntryPath('/auth/login'), {
      isAuthenticated: Boolean(user),
      surface: 'welcome',
      fallbackPath: '/welcome',
    });
    router.push(target as any);
  };

  useEffect(() => {
    if (!coreShellReady) {
      setBackgroundReady(false);
      setDeferredSectionsReady(false);
      return;
    }

    const eagerSection = readUrlSectionIntent();
    if (eagerSection) {
      setBackgroundReady(true);
      setDeferredSectionsReady(true);
      return;
    }

    if (isEmbeddedPreview) {
      setBackgroundReady(true);
      setDeferredSectionsReady(true);
      return;
    }

    let bgTimeout: ReturnType<typeof setTimeout> | null = null;
    let sectionTimeout: ReturnType<typeof setTimeout> | null = null;
    let bgIdleHandle: any = null;
    let sectionIdleHandle: any = null;

    const readyBackground = () => setBackgroundReady(true);
    const readySections = () => setDeferredSectionsReady(true);

    if (isWeb && typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      bgIdleHandle = (window as any).requestIdleCallback(readyBackground, { timeout: 500 });
      sectionIdleHandle = (window as any).requestIdleCallback(readySections, { timeout: 1400 });
    } else {
      bgTimeout = setTimeout(readyBackground, 180);
      sectionTimeout = setTimeout(readySections, 900);
    }

    return () => {
      if (bgTimeout) clearTimeout(bgTimeout);
      if (sectionTimeout) clearTimeout(sectionTimeout);
      if (bgIdleHandle && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        (window as any).cancelIdleCallback(bgIdleHandle);
      }
      if (sectionIdleHandle && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        (window as any).cancelIdleCallback(sectionIdleHandle);
      }
    };
  }, [coreShellReady, isEmbeddedPreview, isWeb, readUrlSectionIntent]);

  // Auto-scroll to section from query/hash (e.g., ?section=pricing or #pricing)
  useEffect(() => {
    if (isWeb && typeof window !== 'undefined' && deferredSectionsReady) {
      const urlSection = readUrlSectionIntent();

      const section = urlSection;
      if (section) {
        if (section === 'pricing') {
          setPricingSurfaceRequested(true);
        }
        let attempt = 0;
        const maxAttempts = 22;
        let retryTimer: ReturnType<typeof setTimeout> | null = null;

        const tryScroll = () => {
          attempt += 1;
          const done = scrollToSection(section);
          if (done) {
            if (section === 'pricing') {
              normalizePricingCompareUrlAfterScroll();
            }
            return;
          }
          if (attempt < maxAttempts) {
            retryTimer = setTimeout(tryScroll, 100);
          }
        };

        retryTimer = setTimeout(tryScroll, 40);
        return () => {
          if (retryTimer) clearTimeout(retryTimer);
        };
      }
    }
  }, [deferredSectionsReady, isWeb, normalizePricingCompareUrlAfterScroll, readUrlSectionIntent, scrollToSection]);

  const pricingSurfaceActive = pricingSurfaceRequested || activeSection === 'pricing';

  useEffect(() => {
    if (latestMediaMentions.length <= 1) return;
    const timer = setInterval(() => {
      setActiveMediaMentionIndex((prev) => (prev + 1) % latestMediaMentions.length);
    }, 4400);
    return () => clearInterval(timer);
  }, [latestMediaMentions]);

  useEffect(() => {
    featuredInOffsetRef.current = 0;
    featuredInMarqueeRef.current?.scrollTo({ x: 0, animated: false });
  }, [featuredInSources, shouldUseFeaturedInAutoMarquee]);

  useEffect(() => {
    if (!shouldUseFeaturedInAutoMarquee || featuredInSources.length <= 1) return;
    const tick = () => {
      if (featuredInPaused) return;
      const baseWidth = marqueeProfile.stepPx;
      const resetAt = featuredInSources.length * baseWidth;
      const next = featuredInOffsetRef.current + baseWidth;
      if (next >= resetAt) {
        featuredInOffsetRef.current = 0;
        featuredInMarqueeRef.current?.scrollTo({ x: 0, animated: false });
        return;
      }
      featuredInOffsetRef.current = next;
      featuredInMarqueeRef.current?.scrollTo({ x: next, animated: true });
    };
    const timer = setInterval(tick, marqueeProfile.intervalMs);
    return () => clearInterval(timer);
  }, [featuredInSources, featuredInPaused, marqueeProfile, shouldUseFeaturedInAutoMarquee]);

  useEffect(() => {
    if (activeSection === 'features') markSummaryInterest('features');
    if (activeSection === 'pricing') markSummaryInterest('pricing');
    if (activeSection === 'social-proof') markSummaryInterest('social-proof');
  }, [activeSection, markSummaryInterest]);

  useEffect(() => {
    if (activeSection === 'features') recordDecisionPathSignal('features', 1);
    if (activeSection === 'pricing') recordDecisionPathSignal('pricing', 1);
    if (activeSection === 'social-proof') recordDecisionPathSignal('social-proof', 1);
  }, [activeSection, recordDecisionPathSignal]);

  const activeMediaMention = latestMediaMentions[activeMediaMentionIndex] || null;
  const heroSummarySourceItems = useMemo(() => {
    const items = heroAsSeenChipItems.slice(0, width < 430 ? 4 : 6);
    return items.map((item, idx) => ({
      id: `${item.slug}-${idx}`,
      label: item.source,
      onPress: () => router.push(`/press/${item.slug}` as any),
    }));
  }, [heroAsSeenChipItems, router, width]);

  const rememberedSummaryInterestCard = useMemo(() => {
    if (!rememberedSummaryInterest) return null;

    if (rememberedSummaryInterest === 'pricing') {
      return {
        title: tx('welcome.hero.summary.memory.pricing.title', 'Your last strong signal was pricing depth'),
        copy: tx('welcome.hero.summary.memory.pricing.copy', 'We’ll keep the commercial path easy to resume, including the plan comparison surface you looked at most recently.'),
        actionLabel: tx('welcome.hero.summary.memory.pricing.action', 'Resume pricing review'),
        onPress: () => navigateToSection('pricing'),
      };
    }

    if (rememberedSummaryInterest === 'social-proof') {
      return {
        title: tx('welcome.hero.summary.memory.social.title', 'Your last strong signal was customer proof'),
        copy: tx('welcome.hero.summary.memory.social.copy', 'We’ll surface the testimonial and trust layer first so you can return to the strongest validation trail.'),
        actionLabel: tx('welcome.hero.summary.memory.social.action', 'Resume proof review'),
        onPress: () => navigateToSection('social-proof'),
      };
    }

    return {
      title: tx('welcome.hero.summary.memory.features.title', 'Your last strong signal was workflow capability'),
      copy: tx('welcome.hero.summary.memory.features.copy', 'We’ll keep the feature path easy to resume so you can jump back into the platform depth that caught your attention.'),
      actionLabel: tx('welcome.hero.summary.memory.features.action', 'Resume features review'),
      onPress: () => navigateToSection('features'),
    };
  }, [navigateToSection, rememberedSummaryInterest, tx]);

  const heroSummarySignals = useMemo(() => ([
    {
      id: 'features',
      label: tx('welcome.hero.summary.signal.features', 'Capability depth'),
      value: tx('welcome.hero.summary.signal.featuresValue', '{count} live workflows').replace('{count}', String(Number(counts.features || 0))),
      tone: 'primary' as const,
      emphasis: rememberedSummaryInterest === 'features',
    },
    {
      id: 'plans',
      label: tx('welcome.hero.summary.signal.plans', 'Commercial layers'),
      value: tx('welcome.hero.summary.signal.plansValue', '{count} plan states').replace('{count}', String(Math.max(Number(canonicalWelcomePlans.length || 0), 3))),
      tone: 'success' as const,
      emphasis: rememberedSummaryInterest === 'pricing',
    },
    {
      id: 'proof',
      label: tx('welcome.hero.summary.signal.proof', 'Proof density'),
      value: tx('welcome.hero.summary.signal.proofValue', '{count} testimonials').replace('{count}', String(Number(welcomeTestimonialsCount || 0))),
      tone: 'warning' as const,
      emphasis: rememberedSummaryInterest === 'social-proof',
    },
    {
      id: 'faq',
      label: tx('welcome.hero.summary.signal.faq', 'Buyer answers'),
      value: tx('welcome.hero.summary.signal.faqValue', '{count} FAQ routes').replace('{count}', String(Number(welcomeFaqItems.length || 0))),
      tone: 'accent' as const,
    },
  ]), [canonicalWelcomePlans.length, counts.features, rememberedSummaryInterest, tx, welcomeFaqItems.length, welcomeTestimonialsCount]);

  const goNewsroomFromHeroSummary = useCallback(() => {
    router.push('/press' as any);
  }, [router]);

  const goTopMediaMention = useCallback(() => {
    if (!activeMediaMention) return;
    router.push(`/press/${activeMediaMention.slug}` as any);
  }, [activeMediaMention, router]);

  const goRegister = (planInfo?: { planId: string; planName: string; planPrice: string; billingPeriod: string }) => {
    markAuthEntryReplaySkipWindow();
    const baseAuthPath = buildAuthEntryPath('/auth/register');
    const [basePath, existingQuery = ''] = baseAuthPath.split('?');
    const params = new URLSearchParams(existingQuery);
    if (planInfo) {
      params.set('planId', planInfo.planId);
      params.set('planName', planInfo.planName);
      params.set('planPrice', planInfo.planPrice);
      params.set('billingPeriod', planInfo.billingPeriod);
      const query = params.toString();
      const target = `${basePath}${query ? `?${query}` : ''}`;
      const safeTarget = resolveVisitorCtaPath(target, {
        isAuthenticated: Boolean(user),
        surface: 'welcome',
        fallbackPath: '/welcome?section=pricing',
      });
      router.push(safeTarget as any);
    } else {
      const query = params.toString();
      const target = `${basePath}${query ? `?${query}` : ''}`;
      const safeTarget = resolveVisitorCtaPath(target, {
        isAuthenticated: Boolean(user),
        surface: 'welcome',
        fallbackPath: '/welcome',
      });
      router.push(safeTarget as any);
    }
  };

  const goAbout = useCallback(() => {
    router.push('/about-us' as any);
  }, [router]);

  const goCareersFromWelcome = useCallback(() => {
    const params = new URLSearchParams();
    params.set('ref', 'welcome-hero');
    params.set('surface', 'welcome');
    void trackCareersEvent({
      event: 'careers_entry_click',
      source: 'welcome-hero',
      page: '/welcome',
      ref: 'welcome-hero',
    });
    router.push(`/careers?${params.toString()}` as any);
  }, [router]);

  const goTalentNetworkFromWelcome = useCallback(() => {
    const params = new URLSearchParams();
    params.set('ref', 'welcome-talent-network');
    params.set('surface', 'welcome');
    void trackCareersEvent({
      event: 'talent_network_entry_click',
      source: 'welcome-careers-banner',
      page: '/welcome',
      ref: 'welcome-talent-network',
    });
    router.push(`/talent-network?${params.toString()}` as any);
  }, [router]);

  if (!coreShellReady) return <WelcomeLandingSkeleton />;

  if (!gpsFallbackActive && gpsLoading && !gpsError) {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg, paddingHorizontal: 16, paddingTop: 20 }}>
        <GpsDataStatusCard
          surfaceName="welcome"
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
            error: C.error,
            success: C.success,
            warning: C.warning,
          }}
          diagnostics={gpsDiagnostics}
          testIdPrefix="welcome"
        />
      </View>
    );
  }

  // GPS label blocker: only show when GPS is in 'live' mode (successful fetch completed)
  // and data is genuinely missing. Never block during bootstrap/degraded modes.
  // This prevents false blockers on cold start before GPS state is populated.
  if (!gpsFallbackActive && missingWelcomeDataKeys.length > 0 && !gpsError && gpsStatus === 'healthy' && gpsDiagnostics?.mode === 'live') {
    return (
      <View style={{ flex: 1, backgroundColor: C.bg }}>
        <GpsLabelBlocker
          surfaceName="welcome"
          missingKeys={missingWelcomeDataKeys}
          colors={{
            bg: C.bg,
            text: C.text,
            textSec: C.textSec,
            textMuted: C.textMuted,
            error: C.error,
            primary: C.primary,
          }}
        />
      </View>
    );
  }

  return (
    <View style={{ flex: 1 }}>
      <View style={s.root} data-testid="welcome-screen" testID="welcome-screen">
        <StatusBar barStyle={isDark ? 'light-content' : 'dark-content'} />

        {gpsError ? (
          <View
            style={{ paddingHorizontal: 16, paddingTop: 12 }}
            data-testid="welcome-inline-gps-status-wrapper"
            testID="welcome-inline-gps-status-wrapper"
          >
            <GpsDataStatusCard
              surfaceName="welcome"
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
                error: C.error,
                success: C.success,
                warning: C.warning,
              }}
              diagnostics={gpsDiagnostics}
              testIdPrefix="welcome"
            />
          </View>
        ) : null}

        {gpsFallbackActive ? (
          <View
            style={{
              marginHorizontal: padding,
              marginTop: 8,
              marginBottom: 2,
              borderRadius: 12,
              borderWidth: 1,
              borderColor: withAlpha(C.warning, '55'),
              backgroundColor: withAlpha(C.warning, '12'),
              paddingHorizontal: 12,
              paddingVertical: 10,
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 10,
            }}
            data-testid="welcome-gps-fallback-banner"
            testID="welcome-gps-fallback-banner"
          >
            <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700', flex: 1 }}>
              {gpsFallbackCopy}
            </Text>
            <TouchableOpacity
              onPress={() => {
                emitWelcomeTelemetry('gps_retry_clicked', { fallback_elapsed_ms: gpsFallbackElapsedMs });
                void gpsRefetch();
              }}
              style={{
                borderRadius: 8,
                borderWidth: 1,
                borderColor: withAlpha(C.primary, '55'),
                backgroundColor: withAlpha(C.primary, '14'),
                paddingHorizontal: 10,
                paddingVertical: 6,
              }}
              data-testid="welcome-gps-fallback-retry-button"
              testID="welcome-gps-fallback-retry-button"
            >
              <Text style={{ color: C.primary, fontSize: 11, fontWeight: '800' }}>{retryLabel}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Language Dropdown Overlay
            Fix (Apr 21 2026): on Expo Web `position: 'absolute'` resolves
            against the scrolling ancestor, so if a mobile user had scrolled
            down and tapped the language button (e.g. via the floating nav),
            the dropdown + outside-click catcher rendered near the scroll
            origin instead of the current viewport. Pin to the viewport on
            web using `position: 'fixed'`; native keeps 'absolute'. */}
        {langMenuOpen && isClient && (
          <>
            <TouchableOpacity
              data-testid="lang-overlay-close"
              testID="lang-overlay-close"
              onPress={() => setLangMenuOpen(false)}
              activeOpacity={1}
              style={{
                ...(Platform.OS === 'web'
                  ? { position: 'fixed' as any }
                  : { position: 'absolute' as any }),
                top: 0, left: 0, right: 0, bottom: 0, zIndex: 9998,
              } as any}
            />
            <View
              data-testid="lang-switcher-dropdown"
              testID="lang-switcher-dropdown"
              style={{
                ...(Platform.OS === 'web'
                  ? { position: 'fixed' as any }
                  : { position: 'absolute' as any }),
                top: 62, right: isDesktop ? 260 : 80, width: 180, borderRadius: 12, overflow: 'hidden', zIndex: 9999, borderWidth: 1, borderColor: isDark ? C.borderMd : C.border, backgroundColor: isDark ? C.border : C.card, ...getShadow('lg', isDark),
              } as any}
            >
              {LANG_OPTIONS.map((lang) => {
                const isActive = languageCode === lang.code;
                return (
                  <TouchableOpacity
                    key={lang.code}
                    data-testid={`lang-option-${lang.code}`} testID={`lang-option-${lang.code}`}
                    onPress={() => { applyLanguageSelection(lang.code, true); }}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 14, backgroundColor: isActive ? (isDark ? C.borderMd : C.border) : 'transparent' }}
                  >
                    <Text style={{ fontSize: 11, fontWeight: '800', color: isActive ? C.primary : (isDark ? C.textMuted : C.textMuted), width: 22, letterSpacing: 0.5 }}>{lang.flag}</Text>
                    <Text style={{ fontSize: 13, fontWeight: isActive ? '700' : '500', color: isActive ? C.primary : C.textMuted, flex: 1 }}>{lang.label}</Text>
                    {isActive && <Ionicons name="checkmark" size={14} color={C.primary} />}
                  </TouchableOpacity>
                );
              })}
            </View>
          </>
        )}

        {/* ─── Full-page floating background image with parallax (client-only to avoid hydration mismatch) ─── */}
        {shouldRenderWebDesktopBg && backgroundLayerReady && (
            <div
            ref={bgRef as any}
            data-testid="welcome-parallax-bg"
            style={{ position: 'absolute', inset: 0, zIndex: 0, willChange: 'transform', transform: 'translateY(0px) scale(1.04)', transition: 'transform 0.1s linear', pointerEvents: 'none', opacity: isDark ? 0.34 : 0.2 } as any}
          >
            <FloatingImageShowcase variant="desktop" isDarkTheme={isDark} />
            <div
              data-testid="welcome-background-image-overlay"
              style={{
                position: 'absolute',
                inset: 0,
                background: isDark
                  ? `linear-gradient(180deg, ${withAlpha(C.bg, 'B6')} 0%, ${withAlpha(C.bg, '9E')} 46%, ${withAlpha(C.bg, 'BC')} 100%)`
                  : `linear-gradient(180deg, ${withAlpha(C.bg, '82')} 0%, ${withAlpha(C.bg, '6A')} 44%, ${withAlpha(C.bg, '8C')} 100%)`,
                zIndex: 2,
                pointerEvents: 'none',
              } as any}
            />
            <div style={{ position: 'absolute', inset: 0, backgroundImage: `linear-gradient(${C.border}55 1px, transparent 1px), linear-gradient(90deg, ${C.border}55 1px, transparent 1px)`, backgroundSize: '72px 72px', opacity: isDark ? 0.08 : 0.14, zIndex: 3, pointerEvents: 'none' } as any} />
          </div>
        )}

        {shouldRenderWebMobileBg && backgroundLayerReady && (
          <div
            data-testid="welcome-mobile-theme-bg"
            style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none', overflow: 'hidden' } as any}
          >
            <FloatingImageShowcase variant="mobile-fullscreen" isDarkTheme={isDark} />
            <div
              data-testid="welcome-mobile-background-image-overlay"
              style={{
                position: 'absolute',
                inset: 0,
                background: isDark ? withAlpha(C.bg, 'AA') : withAlpha(C.bg, '7A'),
                zIndex: 2,
                pointerEvents: 'none',
              } as any}
            />
            <div style={{ position: 'absolute', inset: 0, backgroundImage: `linear-gradient(${C.border}4D 1px, transparent 1px), linear-gradient(90deg, ${C.border}4D 1px, transparent 1px)`, backgroundSize: '48px 48px', opacity: isDark ? 0.1 : 0.16, zIndex: 3, pointerEvents: 'none' } as any} />
          </div>
        )}

        {shouldRenderNativeBg && backgroundLayerReady && (
          <View pointerEvents="none" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 0, overflow: 'hidden' }}>
            <FloatingImageShowcase variant="mobile-fullscreen" isDarkTheme={isDark} />
            <View
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: isDark ? withAlpha(C.bg, 'A8') : withAlpha(C.bg, '74'),
              }}
            />
          </View>
        )}

        <ScrollView
          ref={scrollRef}
          testID="welcome-scroll-view"
          style={[s.scroll, { zIndex: 1 } as any]}
          contentContainerStyle={s.scrollContent}
          showsVerticalScrollIndicator={false}
          onScroll={onScroll}
          scrollEventThrottle={16}
        >
          {/* Navbar */}
          <View style={s.navOuter} data-testid="welcome-nav" testID="welcome-nav">
            <View style={s.navBar}>
              <View style={s.navBrand} data-testid="welcome-logo" testID="welcome-logo">
                <Image
                  source={require('../assets/images/logo.png')}
                  style={{ width: 32, height: 32, borderRadius: 8 }}
                  resizeMode="contain"
                />
                <View data-notranslate>
                  <Text
                    style={s.logoText}
                    data-notranslate
                    data-testid="welcome-brand-name"
                    testID="welcome-brand-name"
                  >
                    {PLATFORM_BRAND.slice(0, 4)}<Text style={{ color: C.accent }}>AI</Text>{PLATFORM_BRAND.slice(6)}
                  </Text>
                </View>
              </View>

              {isDesktop && (
                <View style={s.navLinks}>
                  {NAV_LINKS.map(l => (
                    <TouchableOpacity key={l.section} onPress={() => l.href ? router.push(l.href as any) : navigateToSection(l.section)} {...getTestProps(`welcome-nav-link-${l.section}`)}>
                      <Text style={s.navLink}>{t(`welcome.nav.${l.section}`) || l.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <View style={s.navRight}>
                {isDesktop && (
                  <View style={s.themeToggleGroup} {...getTestProps('welcome-theme-toggle')}>
                    {[
                      { key: 'light', icon: 'sunny' },
                      { key: 'system', icon: 'desktop' },
                      { key: 'dark', icon: 'moon' },
                    ].map(mode => {
                      const active = themeMode === mode.key;
                      return (
                        <TouchableOpacity
                          key={mode.key}
                          onPress={() => setThemeMode(mode.key as any)}
                          style={[s.themeToggle, active && s.themeToggleActive]}
                          {...getTestProps(`welcome-theme-toggle-${mode.key}`)}
                          accessibilityRole="button"
                          accessibilityLabel={tx(`welcome.theme.mode.${mode.key}`, `Switch to ${mode.key} theme`)}
                        >
                          <Ionicons name={mode.icon as any} size={16} color={active ? C.primary : C.textMuted} />
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                )}

                {/* Globe Language Switcher - hide on narrow mobile to make room for Sign In */}
                {(isDesktop || false) && (
                <TouchableOpacity
                  onPress={() => setLangMenuOpen(!langMenuOpen)}
                  data-testid="welcome-language-selector" testID="welcome-language-selector"
                  style={{ flexDirection: 'row', alignItems: 'center', gap: isDesktop ? 4 : 0, paddingHorizontal: isDesktop ? 10 : 8, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: langMenuOpen ? withAlpha(C.primary, '60') : withAlpha(C.borderStrong, '40'), backgroundColor: langMenuOpen ? withAlpha(C.primary, '10') : 'transparent' }}
                >
                  <Ionicons name="globe-outline" size={16} color={langMenuOpen ? C.primary : C.textMuted} />
                  {isDesktop && (
                    <>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: langMenuOpen ? C.primary : C.textMuted, letterSpacing: 0.5 }}>{languageCode.toUpperCase()}</Text>
                      <Ionicons name={langMenuOpen ? 'chevron-up' : 'chevron-down'} size={12} color={langMenuOpen ? C.primary : C.textDim} />
                    </>
                  )}
                </TouchableOpacity>
                )}

                {!isDesktop && (
                  <>
                    <TouchableOpacity onPress={goLogin} data-testid="welcome-mobile-signin-nav" testID="welcome-mobile-signin-nav" style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: C.accent, backgroundColor: withAlpha(C.accent, '15') }}>
                      <Text style={{ color: C.accent, fontSize: 12, fontWeight: '800' }}>{t('welcome.mobile.signIn')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => setMenuOpen(!menuOpen)} data-testid="welcome-nav-hamburger" testID="welcome-nav-hamburger" style={s.hamburger}>
                      <Ionicons name={menuOpen ? 'close' : 'menu'} size={22} color={C.textSec} />
                    </TouchableOpacity>
                  </>
                )}
                {isDesktop && (
                  <>
                    <TouchableOpacity onPress={goLogin} data-testid="welcome-nav-signin" testID="welcome-nav-signin">
                      <Text style={s.navSignIn}>{t('welcome.nav.signIn')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={s.navCTA} onPress={goRegister} data-testid="welcome-nav-signup" testID="welcome-nav-signup">
                      <Text style={s.navCTAText}>{t('welcome.nav.startTrial')}</Text>
                    </TouchableOpacity>
                  </>
                )}
              </View>
            </View>

            {!isDesktop && menuOpen && (
              <View style={s.mobileMenu} data-testid="welcome-mobile-menu" testID="welcome-mobile-menu">
                {NAV_LINKS.map(l => (
                  <TouchableOpacity key={l.section} onPress={() => { setMenuOpen(false); if (l.href) { router.push(l.href as any); return; } navigateToSection(l.section); }} {...getTestProps(`welcome-mobile-link-${l.section}`)}>
                    <Text style={s.mobileLink}>{t(`welcome.nav.${l.section}`) || l.label}</Text>
                  </TouchableOpacity>
                ))}
                <View style={s.mobileDivider} />
                {/* Mobile Theme Toggle */}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 4, paddingVertical: 6 }} data-testid="mobile-theme-toggle" testID="mobile-theme-toggle">
                  <Ionicons name={isDark ? 'moon' : 'sunny'} size={14} color={isDark ? C.textSec : C.textMuted} />
                  <Text style={{ fontSize: 13, fontWeight: '600', color: C.text, flex: 1 }}>{t('welcome.mobile.theme')}</Text>
                  <View style={s.themeToggleGroup} {...getTestProps('welcome-mobile-theme-toggle')}>
                    {[
                      { key: 'light', icon: 'sunny' },
                      { key: 'system', icon: 'desktop' },
                      { key: 'dark', icon: 'moon' },
                    ].map(mode => {
                      const active = themeMode === mode.key;
                      return (
                        <TouchableOpacity
                          key={mode.key}
                          onPress={() => setThemeMode(mode.key as any)}
                          style={[s.themeToggle, active && s.themeToggleActive]}
                          {...getTestProps(`welcome-mobile-theme-${mode.key}`)}
                        >
                          <Ionicons name={mode.icon as any} size={14} color={active ? C.primary : C.textMuted} />
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                </View>
                <View style={s.mobileDivider} />
                {/* Mobile Language Switcher */}
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: 4, paddingVertical: 8 }} data-testid="welcome-mobile-language-selector" testID="welcome-mobile-language-selector">
                  {LANG_OPTIONS.map(lang => {
                    const isActive = languageCode === lang.code;
                    return (
                      <TouchableOpacity
                        key={lang.code}
                        data-testid={`mobile-lang-${lang.code}`} testID={`mobile-lang-${lang.code}`}
                        onPress={() => { applyLanguageSelection(lang.code, false); }}
                        style={{ paddingHorizontal: 12, paddingVertical: 7, borderRadius: 8, borderWidth: 1.5, borderColor: isActive ? C.primary : C.borderBright, backgroundColor: isActive ? withAlpha(C.primary, '14') : (isDark ? C.border : 'transparent') }}
                      >
                        <Text style={{ fontSize: 12, fontWeight: isActive ? '800' : '700', color: isActive ? C.primary : (isDark ? C.text : C.textMuted) }}>{lang.flag}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                <View style={s.mobileDivider} />
                <TouchableOpacity onPress={() => { setMenuOpen(false); goLogin(); }} data-testid="welcome-mobile-signin" testID="welcome-mobile-signin" style={s.mobileBtn}>
                  <Text style={s.mobileBtnText}>{t('welcome.nav.signIn')}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => { setMenuOpen(false); goRegister(); }} style={s.mobileCTA} data-testid="welcome-mobile-signup" testID="welcome-mobile-signup">
                  <Text style={s.mobileCTAText}>{t('welcome.nav.startTrial')}</Text>
                </TouchableOpacity>
              </View>
            )}

            {viewerIsAdmin ? (
              <View
                style={{
                  marginTop: 10,
                  paddingHorizontal: 12,
                  paddingVertical: 8,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: withAlpha(welcomeSystemStatusColor, '40'),
                  backgroundColor: withAlpha(welcomeSystemStatusColor, isDark ? '1E' : '12'),
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 10,
                  flexWrap: 'wrap',
                }}
                data-testid="welcome-system-status-indicator"
                testID="welcome-system-status-indicator"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
                  <View
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 4,
                      backgroundColor: welcomeSystemStatusColor,
                    }}
                    data-testid="welcome-system-status-dot"
                    testID="welcome-system-status-dot"
                  />
                  <Text
                    style={{ color: C.text, fontSize: 12, fontWeight: '800', letterSpacing: 0.4 }}
                    data-testid="welcome-system-status-label"
                    testID="welcome-system-status-label"
                  >
                    {tx('welcome.systemStatus.label', 'System Status')}: {welcomeSystemStatusLabel}
                  </Text>
                </View>
                <Text
                  style={{ color: C.textMuted, fontSize: 11, fontWeight: '700', flexShrink: 1 }}
                  data-testid="welcome-system-status-last-refresh"
                  testID="welcome-system-status-last-refresh"
                >
                  {tx('welcome.systemStatus.updated', 'Updated')} {welcomeLastRefreshLabel}
                </Text>
              </View>
            ) : null}
          </View>

          <View onLayout={(e) => setSectionOffset('hero', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-hero')}>
            <View
              style={{
                width: '100%',
                alignSelf: 'center',
                maxWidth: centeredHeroShellWidth,
              }}
              data-testid="welcome-hero-centered-shell"
              testID="welcome-hero-centered-shell"
            >
              <WelcomeHero key={languageCode} onLogin={goLogin} onRegister={goRegister} featureCount={counts.features} />
            </View>
          </View>

          <ScrollReveal delay={90}>
            <WelcomeHeroSummaryBand
              lastRefreshLabel={welcomeLastRefreshLabel}
              onOpenNewsroom={goNewsroomFromHeroSummary}
              rememberedInterest={rememberedSummaryInterestCard}
              signalItems={heroSummarySignals}
              sourceItems={heroSummarySourceItems}
              statusLabel={welcomeSystemStatusLabel}
              statusTone={heroSummaryBandTone}
              topMention={activeMediaMention ? {
                source: activeMediaMention.source,
                title: activeMediaMention.title,
                onPress: goTopMediaMention,
              } : null}
            />
          </ScrollReveal>

          {/* Trust Strip */}
          <View onLayout={(e) => setSectionOffset('trust', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-trust')}>
            <ScrollReveal delay={100}>
              <View style={s.trustStrip} data-testid="welcome-trust" testID="welcome-trust">
                <Text style={s.trustLabel}>{t('welcome.trust.label')}</Text>
                <View style={s.trustRow}>
                  {trustNames.map((name, i) => (
                    <TouchableOpacity
                      key={`${name}-${i}`}
                      onPress={() => {}}
                      activeOpacity={0.9}
                      style={[s.trustChip, hoveredTrustChip === name && s.trustChipHover]}
                      {...({ onMouseEnter: () => setHoveredTrustChip(name), onMouseLeave: () => setHoveredTrustChip('') } as any)}
                      data-testid={`welcome-trust-company-chip-${i}`}
                      testID={`welcome-trust-company-chip-${i}`}
                    >
                      <Text style={s.trustChipText}>{name}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <View style={s.trustStars}>
                  {[1, 2, 3, 4, 5].map(i => (
                    <Ionicons key={i} name="star" size={14} color={C.warningText} />
                  ))}
                  <Text style={s.trustRating}>4.9/5 {t('welcome.trust.rating')}</Text>
                </View>
                <View style={s.trustLangBadge} data-testid="welcome-trust-languages-badge" testID="welcome-trust-languages-badge">
                  <Ionicons name="globe-outline" size={14} color={C.primary} />
                  <Text style={s.trustLangBadgeText}>
                    {t('welcome.trust.languagesBadge').replace('{count}', String(supportedLanguages.length))}
                  </Text>
                </View>
              </View>
            </ScrollReveal>
          </View>

          <View onLayout={(e) => setSectionOffset('featured-in', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-featured-in')}>
            <ScrollReveal delay={110}>
              <View
                style={{
                  marginHorizontal: padding,
                  marginTop: utilityStripSpacing,
                  maxWidth: tokens.maxWidth,
                  alignSelf: 'center',
                  width: '100%',
                  borderRadius: 14,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  padding: isDesktop ? 14 : (width < 430 ? 10 : 12),
                  gap: 8,
                }}
                data-testid="welcome-featured-in-marquee"
                testID="welcome-featured-in-marquee"
              >
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="welcome-featured-in-title" testID="welcome-featured-in-title">
                    {featuredInTitleLabel}
                  </Text>
                  <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="welcome-featured-in-status" testID="welcome-featured-in-status">
                    {featuredInStatusLabel}
                  </Text>
                </View>

                {shouldUseFeaturedInAutoMarquee ? (
                  <View
                    {...({ onMouseEnter: () => setFeaturedInPaused(true), onMouseLeave: () => setFeaturedInPaused(false) } as any)}
                    data-testid="welcome-featured-in-marquee-track"
                    testID="welcome-featured-in-marquee-track"
                  >
                    <ScrollView
                      horizontal
                      showsHorizontalScrollIndicator={false}
                      ref={featuredInMarqueeRef}
                      data-testid="welcome-featured-in-scroll"
                      testID="welcome-featured-in-scroll"
                      contentContainerStyle={{
                        gap: 8,
                        paddingRight: 12,
                        justifyContent: 'flex-start',
                      }}
                      scrollEventThrottle={16}
                    >
                      {featuredInMarqueeItems.map((item, idx) => (
                        <TouchableOpacity
                          key={`${item.source}-${item.slug}-${idx}`}
                          onPress={() => router.push(`/press/${item.slug}` as any)}
                          onPressIn={() => setFeaturedInPaused(true)}
                          onPressOut={() => setFeaturedInPaused(false)}
                          style={{
                            minWidth: 174,
                            maxWidth: 174,
                            borderRadius: 10,
                            borderWidth: 1,
                            borderColor: C.border,
                            backgroundColor: C.bgSoft,
                            paddingHorizontal: 10,
                            paddingVertical: 8,
                            gap: 4,
                          }}
                          data-testid={`welcome-featured-in-chip-${idx}`}
                          testID={`welcome-featured-in-chip-${idx}`}
                        >
                          <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.7 }}>{item.source}</Text>
                          <Text style={{ color: C.textMuted, fontSize: 10 }}>{item.category}</Text>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                  </View>
                ) : (
                  <View
                    style={{
                      flexDirection: 'row',
                      flexWrap: 'wrap',
                      gap: 8,
                      justifyContent: phoneUtilitySurface ? 'space-between' : 'flex-start',
                    }}
                    data-testid="welcome-featured-in-static-grid"
                    testID="welcome-featured-in-static-grid"
                  >
                    {compactFeaturedInItems.map((item, idx) => (
                      <TouchableOpacity
                        key={`${item.source}-${item.slug}-${idx}`}
                        onPress={() => router.push(`/press/${item.slug}` as any)}
                        style={{
                          width: featuredInCardWidth,
                          minWidth: 0,
                          borderRadius: 12,
                          borderWidth: 1,
                          borderColor: C.border,
                          backgroundColor: C.bgSoft,
                          paddingHorizontal: 12,
                          paddingVertical: 10,
                          gap: 4,
                        }}
                        data-testid={`welcome-featured-in-chip-${idx}`}
                        testID={`welcome-featured-in-chip-${idx}`}
                      >
                        <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.7 }} numberOfLines={1}>{item.source}</Text>
                        <Text style={{ color: C.textMuted, fontSize: 10 }} numberOfLines={1}>{item.category}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
              </View>
            </ScrollReveal>
          </View>

          <View onLayout={(e) => setSectionOffset('media', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-media-mentions')}>
            <ScrollReveal delay={120}>
              <View
                style={{
                  marginHorizontal: padding,
                  marginTop: utilityStripSpacing,
                  maxWidth: tokens.maxWidth,
                  alignSelf: 'center',
                  width: '100%',
                  borderRadius: 14,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  padding: isDesktop ? 14 : (width < 430 ? 10 : 12),
                  gap: 8,
                }}
                data-testid="welcome-media-mentions-strip"
                testID="welcome-media-mentions-strip"
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                  <Text style={{ color: C.text, fontSize: 13, fontWeight: '800' }} data-testid="welcome-media-mentions-title" testID="welcome-media-mentions-title">
                    {mediaMentionsTitleLabel}
                  </Text>
                  <TouchableOpacity
                    onPress={() => router.push('/press' as any)}
                    style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: phoneUtilitySurface ? 10 : 11, paddingVertical: 6 }}
                    data-testid="welcome-media-mentions-view-all"
                    testID="welcome-media-mentions-view-all"
                  >
                    <Text style={{ color: C.textSec, fontSize: 10, fontWeight: '800' }}>{mediaViewNewsroomLabel}</Text>
                  </TouchableOpacity>
                </View>

                {activeMediaMention ? (
                  <TouchableOpacity
                    onPress={() => router.push(`/press/${activeMediaMention.slug}` as any)}
                    style={{ borderRadius: 12, borderWidth: 1, borderColor: C.border, backgroundColor: C.bg, padding: 11, gap: 5 }}
                    data-testid="welcome-media-mentions-active-card"
                    testID="welcome-media-mentions-active-card"
                  >
                    <Text style={{ color: C.primary, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.7 }} data-testid="welcome-media-mention-source" testID="welcome-media-mention-source">
                      {activeMediaMention.source}
                    </Text>
                    <Text style={{ color: C.text, fontSize: 14, fontWeight: '800', lineHeight: 20 }} numberOfLines={compactUtilitySurface ? 2 : 3} data-testid="welcome-media-mention-title" testID="welcome-media-mention-title">
                      {activeMediaMention.title}
                    </Text>
                    <Text style={{ color: C.textSec, fontSize: 11, lineHeight: 18 }} numberOfLines={compactUtilitySurface ? 3 : 4} data-testid="welcome-media-mention-excerpt" testID="welcome-media-mention-excerpt">
                      {activeMediaMention.excerpt}
                    </Text>
                    <Text style={{ color: C.textMuted, fontSize: 10 }} numberOfLines={2} data-testid="welcome-media-mention-meta" testID="welcome-media-mention-meta">
                      {activeMediaMention.date_label} • {activeMediaMention.category} • {mediaRotationLabel}
                    </Text>
                  </TouchableOpacity>
                ) : null}

                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }} data-testid="welcome-media-mention-pagination" testID="welcome-media-mention-pagination">
                  {latestMediaMentions.map((mention, idx) => {
                    const active = idx === activeMediaMentionIndex;
                    return (
                      <TouchableOpacity
                        key={`${mention.slug}-${idx}`}
                        onPress={() => setActiveMediaMentionIndex(idx)}
                        style={{
                          borderRadius: 999,
                          borderWidth: 1,
                          borderColor: active ? C.primary : C.border,
                          backgroundColor: active ? withAlpha(C.primary, '14') : C.bg,
                          paddingHorizontal: 8,
                          paddingVertical: 4,
                        }}
                        data-testid={`welcome-media-mention-dot-${idx}`}
                        testID={`welcome-media-mention-dot-${idx}`}
                      >
                        <Text style={{ color: active ? C.primary : C.textMuted, fontSize: 10, fontWeight: '700' }}>{idx + 1}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            </ScrollReveal>
          </View>

          {sectionsReady && (
            <>
              <View onLayout={(e) => setSectionOffset('analytics', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-analytics')}>
                <ScrollReveal delay={0} direction="up">
                  <View style={s.enterpriseSectionCard} data-testid="welcome-enterprise-section-analytics" testID="welcome-enterprise-section-analytics">
                    <WelcomeMetrics />
                  </View>
                </ScrollReveal>
              </View>
              <View onLayout={(e) => setSectionOffset('features', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-features')}>
                <ScrollReveal delay={0} direction="up" distance={50}>
                  <View style={s.enterpriseSectionCard} data-testid="welcome-enterprise-section-features" testID="welcome-enterprise-section-features">
                    <WelcomeBenefits onDecisionPathSignal={recordDecisionPathSignal} />
                  </View>
                </ScrollReveal>
              </View>
              <View onLayout={(e) => setSectionOffset('social-proof', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-social-proof')}>
                <ScrollReveal delay={0} direction="up">
                  <View style={s.enterpriseSectionCard} data-testid="welcome-enterprise-section-social" testID="welcome-enterprise-section-social">
                    <WelcomeSocial
                      testimonials={canonicalWelcomeTestimonials}
                      activeSegment={activeTestimonialSegment}
                      onActiveSegmentChange={setActiveTestimonialSegment}
                      onDecisionPathSignal={recordDecisionPathSignal}
                    />
                  </View>
                </ScrollReveal>
              </View>
              <View onLayout={(e) => setSectionOffset('pricing', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-pricing')}>
                <ScrollReveal delay={0} direction="up" distance={50}>
                  <View
                    style={[
                      s.enterpriseSectionCard,
                      pricingSurfaceActive ? s.enterpriseSectionCardPricingActive : null,
                    ]}
                    data-testid="welcome-enterprise-section-pricing"
                    testID="welcome-enterprise-section-pricing"
                  >
                    <View
                      style={[
                        s.pricingSurfaceIndicator,
                        pricingSurfaceActive ? s.pricingSurfaceIndicatorActive : null,
                      ]}
                      data-testid="welcome-pricing-surface-indicator"
                      testID="welcome-pricing-surface-indicator"
                    >
                      <Text
                        style={[
                          s.pricingSurfaceIndicatorText,
                          pricingSurfaceActive ? s.pricingSurfaceIndicatorTextActive : null,
                        ]}
                        data-testid="welcome-pricing-surface-indicator-text"
                        testID="welcome-pricing-surface-indicator-text"
                      >
                        {pricingSurfaceActive
                          ? tx('welcome.pricing.surface.active', 'Pricing section active')
                          : tx('welcome.pricing.surface.idle', 'Pricing section')}
                      </Text>
                    </View>
                    <WelcomePricing onRegister={goRegister} plans={canonicalWelcomePlans} onDecisionPathSignal={recordDecisionPathSignal} />
                  </View>
                </ScrollReveal>
              </View>
              <View onLayout={(e) => setSectionOffset('security', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-security')}>
                <ScrollReveal delay={0} direction="up">
                  <View style={s.enterpriseSectionCard} data-testid="welcome-enterprise-section-faq" testID="welcome-enterprise-section-faq">
                    <WelcomeFAQ
                      faqItems={welcomeFaqItems}
                      activeCategory={activeFaqCategory}
                      onActiveCategoryChange={setActiveFaqCategory}
                      recommenderSegments={testimonialSegments}
                    />
                  </View>
                </ScrollReveal>
              </View>
              <View onLayout={(e) => setSectionOffset('cta', e.nativeEvent.layout.y)} {...getTestProps('welcome-section-cta')}>
                <ScrollReveal delay={0} direction="up">
                  <View style={s.enterpriseSectionCard} data-testid="welcome-enterprise-section-cta" testID="welcome-enterprise-section-cta">
                    <WelcomeCTA
                      onRegister={goRegister}
                      onLogin={goLogin}
                      onOpenAbout={goAbout}
                      decisionPath={decisionPathMemory ? {
                        areaId: decisionPathMemory.topAreaId,
                        scores: decisionPathMemory.scores,
                      } : null}
                    />
                  </View>
                </ScrollReveal>
              </View>

              <View
                style={{
                  marginHorizontal: padding,
                  marginTop: lowerWelcomeSpacing,
                  marginBottom: 8,
                  maxWidth: tokens.maxWidth,
                  alignSelf: 'center',
                  width: '100%',
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.card,
                  borderRadius: 12,
                  overflow: 'hidden',
                }}
                data-testid="welcome-careers-banner"
                testID="welcome-careers-banner"
              >
                <View
                  style={{
                    padding: useWideLowerWelcomeLayout ? 28 : (width < 430 ? 16 : 20),
                    gap: 12,
                    alignItems: shouldCenterCareersBanner ? 'center' : 'flex-start',
                    width: '100%',
                    maxWidth: careersContentMaxWidth,
                    alignSelf: 'center',
                    justifyContent: 'center',
                  }}
                  data-testid="welcome-careers-body"
                  testID="welcome-careers-body"
                >
                  <Text style={{ color: C.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase', textAlign: shouldCenterCareersBanner ? 'center' : 'left' }}>
                    {careersEyebrow}
                  </Text>
                  <Text style={{ color: C.text, fontSize: useWideLowerWelcomeLayout ? 30 : 24, fontWeight: '800', letterSpacing: -0.6, lineHeight: useWideLowerWelcomeLayout ? 36 : 30, textAlign: shouldCenterCareersBanner ? 'center' : 'left' }} data-testid="welcome-careers-title" testID="welcome-careers-title">
                    {careersTitle}
                  </Text>
                  <Text style={{ color: C.textSec, fontSize: 14, lineHeight: 22, maxWidth: shouldCenterCareersBanner ? 640 : 960, textAlign: shouldCenterCareersBanner ? 'center' : 'left' }} data-testid="welcome-careers-copy" testID="welcome-careers-copy">
                    {careersCopy}
                  </Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4, justifyContent: shouldCenterCareersBanner ? 'center' : 'flex-start' }} data-testid="welcome-careers-actions" testID="welcome-careers-actions">
                    <TouchableOpacity
                      onPress={goCareersFromWelcome}
                      style={{
                        backgroundColor: C.primary,
                        paddingHorizontal: width < 430 ? 14 : 18,
                        paddingVertical: 11,
                        borderRadius: 10,
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 8,
                      }}
                      data-testid="welcome-careers-cta"
                      testID="welcome-careers-cta"
                    >
                      <Ionicons name="briefcase-outline" size={15} color={C.primaryText} />
                      <Text style={{ color: C.primaryText, fontSize: 13, fontWeight: '800' }}>{careersExploreLabel}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={goTalentNetworkFromWelcome}
                      style={{
                        borderWidth: 1,
                        borderColor: C.border,
                        backgroundColor: C.card,
                        paddingHorizontal: width < 430 ? 12 : 14,
                        paddingVertical: 11,
                        borderRadius: 10,
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                      }}
                      data-testid="welcome-talent-network-cta"
                      testID="welcome-talent-network-cta"
                    >
                      <Ionicons name="sparkles-outline" size={14} color={C.textSec} />
                      <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{careersTalentLabel}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => router.push('/track-application' as any)}
                      style={{
                        borderWidth: 1,
                        borderColor: C.border,
                        backgroundColor: C.bgSoft,
                        paddingHorizontal: width < 430 ? 12 : 14,
                        paddingVertical: 11,
                        borderRadius: 10,
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 6,
                      }}
                      data-testid="welcome-track-application-cta"
                      testID="welcome-track-application-cta"
                    >
                      <Ionicons name="locate-outline" size={14} color={C.textSec} />
                      <Text style={{ color: C.textSec, fontSize: 12, fontWeight: '700' }}>{careersTrackLabel}</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>

              {/* Footer */}
              <ScrollReveal delay={0} direction="up" distance={30}>
                <View
                  style={{ paddingTop: Math.max(0, lowerWelcomeSpacing - 4), paddingBottom: width < 768 ? 36 : isDesktop ? 0 : 48 }}
                  data-testid="welcome-footer-wrapper"
                  testID="welcome-footer-wrapper"
                  onLayout={(event) => {
                    const nextY = Number(event?.nativeEvent?.layout?.y ?? 0);
                    if (Number.isFinite(nextY) && nextY > 0) {
                      footerOffsetRef.current = nextY;
                    }
                  }}
                >
                  <Footer variant="welcome" key={`footer-${languageCode}`} />
                </View>
              </ScrollReveal>
            </>
          )}
        </ScrollView>

        <SectionProgressRail
          visible={showProgressRail}
          colors={{ ...C, surface: C.surface }}
          railTestId="welcome-progress-rail"
          activeId={activeSection}
          onSelect={scrollToSection}
          top={148}
          right={Math.max(10, padding - 6)}
          maxWidth={132}
          items={[
            { id: 'hero', label: tx('welcome.progress.hero', 'Hero') },
            { id: 'trust', label: tx('welcome.progress.trust', 'Trust') },
            { id: 'featured-in', label: tx('welcome.progress.featured', 'Featured') },
            { id: 'media', label: tx('welcome.progress.media', 'Media') },
            { id: 'analytics', label: tx('welcome.progress.analytics', 'Analytics') },
            { id: 'features', label: tx('welcome.progress.features', 'Features') },
            { id: 'social-proof', label: tx('welcome.progress.social', 'Social') },
            { id: 'pricing', label: tx('welcome.progress.pricing', 'Pricing') },
            { id: 'security', label: tx('welcome.progress.security', 'Security') },
            { id: 'cta', label: tx('welcome.progress.cta', 'CTA') },
          ]}
        />

        {isDesktop && !suppressFloatingChrome && !hideDesktopQuickNavByViewport ? (
          <View
            style={{
              position: 'fixed' as any,
              right: Math.max(12, padding - 4),
              bottom: 24,
              width: 'min(212px, calc(100vw - 24px))' as any,
              borderRadius: 18,
              borderWidth: 1,
              borderColor: C.border,
              backgroundColor: `${C.card}F4`,
              paddingHorizontal: 12,
              paddingVertical: 12,
              gap: 9,
              alignItems: 'center' as any,
              zIndex: 120,
              boxShadow: `0 18px 40px ${withAlpha(C.shadowColor, isDark ? '52' : '1A')}`,
            }}
            data-testid="welcome-sticky-quick-navigator"
            testID="welcome-sticky-quick-navigator"
          >
            <View style={{ gap: 4, alignItems: 'center' as any }}>
              <Text style={{ color: C.text, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1.1, textAlign: 'center' as any }} data-testid="welcome-sticky-quick-navigator-title" testID="welcome-sticky-quick-navigator-title">{quickNavigatorLabel}</Text>
              <Text style={{ color: C.textMuted, fontSize: 10, lineHeight: 15, textAlign: 'center' as any, maxWidth: 172 }} data-testid="welcome-sticky-quick-navigator-copy" testID="welcome-sticky-quick-navigator-copy">{quickNavigatorCopy}</Text>
            </View>
            <View style={{ gap: 6, alignItems: 'center' as any }}>
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, textAlign: 'center' as any }}>{quickNavigatorFaqLabel}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5, justifyContent: 'center' as any, maxWidth: '100%' as any }} data-testid="welcome-sticky-quick-navigator-faq-row" testID="welcome-sticky-quick-navigator-faq-row">
              {faqCategories.slice(0, 4).map((category, idx) => (
                <TouchableOpacity
                  key={`${category}-${idx}`}
                  onPress={() => {
                    setActiveFaqCategory(category);
                    navigateToSection('security');
                  }}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 5 }}
                  data-testid={`welcome-quick-nav-faq-chip-${idx}`}
                  testID={`welcome-quick-nav-faq-chip-${idx}`}
                >
                  <Text style={{ color: C.textSec, fontSize: 8.5, fontWeight: '700' }}>{quickNavChipLabel(category)}</Text>
                </TouchableOpacity>
              ))}
            </View>
            </View>
            <View style={{ height: 1, backgroundColor: C.border, opacity: 0.7 }} />
            <View style={{ gap: 6, alignItems: 'center' as any }}>
              <Text style={{ color: C.textMuted, fontSize: 9, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8, textAlign: 'center' as any }}>{quickNavigatorTestimonialLabel}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 5, justifyContent: 'center' as any, maxWidth: '100%' as any }} data-testid="welcome-sticky-quick-navigator-testimonial-row" testID="welcome-sticky-quick-navigator-testimonial-row">
              {testimonialSegments.slice(0, 4).map((segment, idx) => (
                <TouchableOpacity
                  key={`${segment}-${idx}`}
                  onPress={() => {
                    setActiveTestimonialSegment(segment);
                    navigateToSection('social-proof');
                  }}
                  style={{ borderRadius: 999, borderWidth: 1, borderColor: C.border, backgroundColor: C.bgSoft, paddingHorizontal: 8, paddingVertical: 5 }}
                  data-testid={`welcome-quick-nav-testimonial-chip-${idx}`}
                  testID={`welcome-quick-nav-testimonial-chip-${idx}`}
                >
                  <Text style={{ color: C.textSec, fontSize: 8.5, fontWeight: '700' }}>{quickNavChipLabel(segment)}</Text>
                </TouchableOpacity>
              ))}
            </View>
            </View>
          </View>
        ) : null
        }

      </View>
    </View>
  );
}

function makeStyles(C: any, isDark: boolean, horizontalPadding: number, tokens: GLSTokens) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: C.bg, position: 'relative', overflow: 'hidden' },
    scroll: { flex: 1 },
    scrollContent: { paddingBottom: 12 },
    navOuter: {
      paddingHorizontal: horizontalPadding,
      paddingTop: 14,
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      width: '100%',
    },
    navBar: { flexDirection: 'row', flexWrap: 'wrap', rowGap: 8, alignItems: 'center', justifyContent: 'space-between', paddingVertical: 11, paddingHorizontal: horizontalPadding <= 16 ? 10 : 14, borderRadius: 12, backgroundColor: isDark ? `${C.surface}F2` : `${C.surface}E8`, borderWidth: 1, borderColor: C.borderMd, ...blur, ...getShadow('sm', isDark) },
    navBrand: { flexDirection: 'row', alignItems: 'center', gap: 10, minWidth: 0, flexShrink: 1 },
    logoText: { color: C.text, fontSize: 18, fontWeight: '800', letterSpacing: -0.3, flexShrink: 1 },
    navLinks: { flexDirection: 'row', gap: 20, flexWrap: 'wrap', justifyContent: 'flex-end' },
    navLink: { color: C.textSec, fontSize: 14, fontWeight: '600' },
    navRight: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end', minWidth: 0 },
    navSignIn: { color: C.textSec, fontSize: 14, fontWeight: '700' },
    navCTA: { paddingHorizontal: 22, paddingVertical: 10, borderRadius: 8, backgroundColor: C.accent },
    navCTAText: { color: C.primaryText, fontSize: 13, fontWeight: '700' },
    hamburger: { padding: 4 },
    themeToggleGroup: { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 4, borderRadius: 12, backgroundColor: C.bgAlt, borderWidth: 1, borderColor: C.border },
    themeToggle: { width: 34, height: 34, borderRadius: 10, backgroundColor: 'transparent', borderWidth: 1, borderColor: 'transparent', alignItems: 'center', justifyContent: 'center' },
    themeToggleActive: { backgroundColor: C.surface, borderColor: C.borderMd, ...getShadow('sm', isDark) },

    mobileMenu: { marginTop: 8, backgroundColor: C.surfaceHover, borderRadius: 16, borderWidth: 1, borderColor: C.borderMd, padding: horizontalPadding <= 16 ? 12 : 16, gap: 4, ...blur, ...getShadow('md', isDark) },
    mobileLink: { color: C.text, fontSize: 15, fontWeight: '600', paddingVertical: 12, paddingHorizontal: 8 },
    mobileDivider: { height: 1, backgroundColor: C.borderMd, marginVertical: 8 },
    mobileBtn: { paddingVertical: 12, alignItems: 'center', borderRadius: 10, borderWidth: 1.5, borderColor: C.borderBright, marginTop: 4 },
    mobileBtnText: { color: C.text, fontSize: 14, fontWeight: '700' },
    mobileCTA: { paddingVertical: 12, alignItems: 'center', borderRadius: 10, backgroundColor: C.accent, marginTop: 8 },
    mobileCTAText: { color: C.primaryText, fontSize: 14, fontWeight: '700' },

    trustStrip: {
      paddingVertical: horizontalPadding <= 16 ? 24 : 34,
      paddingHorizontal: horizontalPadding,
      alignItems: 'center',
      borderTopWidth: 1,
      borderBottomWidth: 1,
      borderColor: C.border,
      maxWidth: tokens.maxWidth,
      alignSelf: 'center',
      width: '100%',
      backgroundColor: isDark ? `${C.surface}73` : `${C.surface}B8`,
    },
    trustLabel: { color: C.textMuted, fontSize: 11, fontWeight: '800', letterSpacing: 2.5, marginBottom: 20 },
    trustRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: horizontalPadding <= 16 ? 8 : 10, marginBottom: 18 },
    trustChip: { paddingHorizontal: horizontalPadding <= 16 ? 12 : 18, paddingVertical: 9, borderRadius: 8, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, maxWidth: '100%', ...getShadow('sm', isDark) },
    trustChipHover: { backgroundColor: C.bgSoft, borderColor: C.primary },
    trustChipText: { color: C.textSec, fontSize: 13, fontWeight: '700', letterSpacing: 0.3 },
    trustStars: { flexDirection: 'row', alignItems: 'center', gap: 3 },
    trustRating: { color: C.textSec, fontSize: 13, fontWeight: '600', marginLeft: 8 },
    trustLangBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 14, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: `${C.primary}55`, backgroundColor: isDark ? `${C.primary}1F` : `${C.primary}12` },
    trustLangBadgeText: { color: C.primary, fontSize: 12, fontWeight: '800', letterSpacing: 0.4 },

    enterpriseSectionCard: {
      marginHorizontal: horizontalPadding,
      marginTop: horizontalPadding <= 16 ? 12 : 14,
      borderRadius: 18,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: isDark ? `${C.surface}E3` : `${C.surface}F0`,
      paddingVertical: horizontalPadding <= 16 ? 8 : 12,
      overflow: 'hidden',
      ...blur,
      ...getShadow('sm', isDark),
    },
    enterpriseSectionCardPricingActive: {
      borderColor: C.primary,
      borderWidth: 1.6,
      backgroundColor: isDark ? `${C.surface}F0` : `${C.surface}F8`,
      ...getShadow('md', isDark),
    },
    pricingSurfaceIndicator: {
      alignSelf: 'flex-start',
      marginLeft: 12,
      marginTop: 6,
      marginBottom: 2,
      paddingHorizontal: 10,
      paddingVertical: 5,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.bgSoft,
    },
    pricingSurfaceIndicatorActive: {
      borderColor: C.primary,
      backgroundColor: `${C.primary}20`,
    },
    pricingSurfaceIndicatorText: {
      fontSize: 10,
      fontWeight: '800',
      letterSpacing: 0.5,
      textTransform: 'uppercase',
      color: C.textMuted,
    },
    pricingSurfaceIndicatorTextActive: {
      color: C.primary,
    },

    progressRail: {
      position: 'absolute',
      right: Math.max(12, horizontalPadding - 8),
      top: 148,
      zIndex: 4,
      borderRadius: 12,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: isDark ? `${C.surface}E6` : `${C.surface}F0`,
      padding: 8,
      gap: 6,
      ...blur,
      ...getShadow('md', isDark),
    },
    progressRailItem: {
      borderRadius: 8,
      paddingHorizontal: 10,
      paddingVertical: 7,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: 'transparent',
    },
    progressRailItemActive: {
      borderColor: C.primary,
      backgroundColor: `${C.primary}20`,
    },
    progressRailLabel: {
      fontSize: 10,
      fontWeight: '700',
      color: C.textMuted,
      letterSpacing: 0.3,
    },
    progressRailLabelActive: {
      color: C.primary,
    },

    footer: { /* removed - using shared Footer component */ },
    footerInner: {},
    footerBrand: {},
    footerBrandRow: {},
    footerLogo: { color: C.text, fontSize: 17, fontWeight: '800' },
    footerTagline: { color: C.textMuted, fontSize: 13, lineHeight: 20, maxWidth: 280 },
    footerCol: {},
    footerColTitle: { color: C.textSec, fontSize: 13, fontWeight: '700', marginBottom: 4, letterSpacing: 0.3 },
    footerLink: { color: C.textMuted, fontSize: 13 },
    footerBottom: {},
    footerCopy: { color: C.textMuted, fontSize: 12 },
    footerSocials: { flexDirection: 'row', gap: 8 },
    footerSocial: { width: 32, height: 32, borderRadius: 10, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, alignItems: 'center', justifyContent: 'center', ...getShadow('sm', isDark) },
  });
}
