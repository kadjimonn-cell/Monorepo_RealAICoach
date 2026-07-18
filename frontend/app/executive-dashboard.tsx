import React, { useEffect, useState, useCallback, Suspense} from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, useWindowDimensions, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '../src/context/AuthContext';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';
import api from '../src/services/api';
import { trackTabAliasHit } from '../src/services/tabAliasTelemetry';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useExecStyles } from '../src/components/admin/ExecDashboardPanels';
import { ExecutiveDashboardSkeleton, FadeSlideIn } from '../src/components/SkeletonLoaders';
import AppShell from '../src/components/AppShell';
import { getAdminColors } from '../src/hooks/useAdminTheme';
import {
  CONSOLE_TAB_DEBUG_VERSIONS,
  EXEC_SECTION_ALIASES_FROM_OPERATIONS,
  EXEC_SECTION_LEGACY_ALIASES,
} from '../src/lib/consoleTabContracts';
import TabMergeHubPanel from '../src/components/admin/TabMergeHubPanel';
import {
  EXECUTIVE_PHASE_B_HUBS,
  EXECUTIVE_LEGACY_TAB_TO_HUB,
  getExecutiveHubById,
} from '../src/config/phaseBTabConsolidation';

// Extracted components
import { ExecSearchModal } from '../src/components/executive/ExecSearchModal';
import { ExecOverviewSection } from '../src/components/executive/ExecOverviewSection';
import {
  ExecJobControlPanel, ExecUserManagementPanel,
  ExecIDVerificationPanel, ExecContentPanel, ExecLogsPanel,
} from '../src/components/executive/ExecInlinePanels';
import { ExecShortcutSheet } from '../src/components/executive/ExecShortcutSheet';
import EnterpriseSignOutConfirmModal from '../src/components/auth/EnterpriseSignOutConfirmModal';
import GtecDirectiveBanner from '../src/components/admin/GtecDirectiveBanner';
import { WebOnlyScreen } from '../src/components/WebOnlyScreen';
import GtecScanV2Panel from '../src/components/admin/GtecScanV2Panel';
import GtecUpstreamWatchdogPanel from '../src/components/admin/GtecUpstreamWatchdogPanel';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

// Lazy-load heavy admin panels
const SecurityDashboardPanel = React.lazy(() => import('../src/components/admin/SecurityDashboardPanel'));
const PdfPolicyMonitorPanel = React.lazy(() => import('../src/components/admin/PdfPolicyMonitorPanel'));
const ComplianceDigestHubPanel = React.lazy(() => import('../src/components/admin/ComplianceDigestHubPanel'));
const PublicCoachingTipsPanel = React.lazy(() => import('../src/components/admin/PublicCoachingTipsPanel'));
const TickertapeAnalyticsPanel = React.lazy(() => import('../src/components/admin/TickertapeAnalyticsPanel'));
const UnifiedSupportPanel = React.lazy(() => import('../src/components/admin/UnifiedSupportPanel'));
const EmailTemplatesPanel = React.lazy(() => import('../src/components/admin/EmailTemplatesPanel'));
const SessionManagementPanel = React.lazy(() => import('../src/components/admin/SessionManagementPanel'));
const SubscriptionAnalyticsPanel = React.lazy(() => import('../src/components/admin/SubscriptionAnalyticsPanel'));
const AttachmentLightbox = React.lazy(() => import('../src/components/admin/AttachmentLightbox'));
const ThemeValidationDashboard = React.lazy(() => import('../src/components/admin/ThemeValidationDashboard'));
const OnboardingAnalyticsPanel = React.lazy(() => import('../src/components/admin/OnboardingAnalyticsPanel'));
const SSOAnalyticsPanel = React.lazy(() => import('../src/components/admin/SSOAnalyticsPanel'));
const CsatDashboardPanel = React.lazy(() => import('../src/components/admin/CsatDashboardPanel'));
const TicketFeedbackIntelPanel = React.lazy(() => import('../src/components/admin/TicketFeedbackIntelPanel'));
const NewsletterAnalyticsPanel = React.lazy(() => import('../src/components/admin/NewsletterAnalyticsPanelV2'));
const ConversionAnalyticsPanel = React.lazy(() => import('../src/components/admin/ConversionAnalyticsPanel'));
const PromptABTestingPanel = React.lazy(() => import('../src/components/admin/PromptABTestingPanel'));
const ContentStudioAnalyticsPanel = React.lazy(() => import('../src/components/admin/ContentStudioAnalyticsPanel'));
const RevenuePanel = React.lazy(() => import('../src/components/admin/RevenuePanel'));
const AIAutoSupportPanel = React.lazy(() => import('../src/components/admin/AIAutoSupportPanel'));
const FraudDetectionPanel = React.lazy(() => import('../src/components/admin/FraudDetectionPanel'));
const SIEMPanel = React.lazy(() => import('../src/components/admin/SIEMPanel'));
const SLAMonitorPanel = React.lazy(() => import('../src/components/admin/SLAMonitorPanel'));
const OTPDeliveryDashboardPanel = React.lazy(() => import('../src/components/admin/OTPDeliveryDashboardPanel'));
const WebhookEventStreamPanel = React.lazy(() => import('../src/components/admin/WebhookEventStreamPanel'));
const NotificationManagementPanel = React.lazy(() => import('../src/components/admin/NotificationManagementPanel'));
const PerformanceDashboardPanel = React.lazy(() => import('../src/components/admin/PerformanceDashboardPanel'));
const PagePerformancePanel = React.lazy(() => import('../src/components/admin/PagePerformancePanel'));
const EmployerPortalPanel = React.lazy(() => import('../src/components/admin/EmployerPortalPanel'));
const LeaderboardManagementPanel = React.lazy(() => import('../src/components/admin/LeaderboardManagementPanel'));
const IntegrationManagementPanel = React.lazy(() => import('../src/components/admin/IntegrationManagementPanel'));
const SubscriptionPlanManagementPanel = React.lazy(() => import('../src/components/admin/SubscriptionPlanManagementPanel'));
const PaymentBillingPanel = React.lazy(() => import('../src/components/admin/PaymentBillingPanel'));
const IAPManagementPanel = React.lazy(() => import('../src/components/admin/IAPManagementPanel'));
const UnifiedRevenuePanel = React.lazy(() => import('../src/components/admin/UnifiedRevenuePanel'));
const CompetitorKeywordPanel = React.lazy(() => import('../src/components/admin/CompetitorKeywordPanel'));
const CDNManagementPanel = React.lazy(() => import('../src/components/admin/CDNManagementPanel'));
const EnterpriseSecurityPanel = React.lazy(() => import('../src/components/admin/EnterpriseSecurityPanel'));
const AutomationEnginePanel = React.lazy(() => import('../src/components/admin/AutomationEnginePanel'));
const AICommandCenterPanel = React.lazy(() => import('../src/components/admin/AICommandCenterPanel'));
const GlobalAdaptationControlCenterPanel = React.lazy(() => import('../src/components/admin/GlobalAdaptationControlCenterPanel'));
const EmailCoverageMatrixPanel = React.lazy(() => import('../src/components/admin/EmailCoverageMatrixPanel'));
const FeedbackHeatmapPanel = React.lazy(() => import('../src/components/admin/FeedbackHeatmapPanel'));
const DeviceAuditPanel = React.lazy(() => import('../src/components/admin/DeviceAuditPanel'));
// SupportTicketPanel now part of UnifiedSupportPanel
const PlatformSettingsEnterpriseWorkspace = React.lazy(() => import('../src/components/executive/PlatformSettingsEnterpriseWorkspace'));
const LegalUpdateEnterpriseWorkspace = React.lazy(() => import('../src/components/executive/LegalUpdateEnterpriseWorkspace'));
const EmailGuardrailControlCenterWorkspace = React.lazy(() => import('../src/components/executive/EmailGuardrailControlCenterWorkspace'));
const RevenueBillingEnterpriseWorkspace = React.lazy(() => import('../src/components/executive/RevenueBillingEnterpriseWorkspace'));
const LearningHubAutopilotExecutiveWorkspace = React.lazy(() => import('../src/components/executive/LearningHubAutopilotExecutiveWorkspace'));
let SystemMonitorPanel: any = null;
if (Platform.OS === 'web') {
  SystemMonitorPanel = React.lazy(() => import('../src/components/admin/SystemMonitorPanel'));
}

function LazyFallback() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const text = t('executive.loadingPanel');
  return (
    <View style={{ padding: 40, alignItems: 'center', justifyContent: 'center' }}>
      <ActivityIndicator size="large" color={colors.primary} />
      <Text style={{ color: colors.textSec, marginTop: 12, fontSize: 13 }}>{text === 'executive.loadingPanel' ? 'Loading panel...' : text}</Text>
    </View>
  );
}

const getExecHubTab = (hubId: string) => {
  const hub = EXECUTIVE_PHASE_B_HUBS.find((item) => item.id === hubId);
  if (!hub) {
    return { id: hubId, label: hubId, icon: 'ellipse' };
  }
  return { id: hub.id, label: hub.label, icon: hub.icon };
};

const CATEGORY_TABS: Record<string, { id: string; label: string; icon: string; route?: string }[]> = {
  overview: [
    getExecHubTab('exec-command-center'),
    getExecHubTab('exec-ai-operations-hub'),
  ],
  growth: [
    getExecHubTab('exec-growth-experimentation-hub'),
    getExecHubTab('exec-revenue-billing-hub'),
  ],
  hiring: [
    getExecHubTab('exec-hiring-careers-hub'),
    getExecHubTab('exec-notifications-support-hub'),
  ],
  security: [
    getExecHubTab('exec-security-trust-hub'),
    getExecHubTab('exec-identity-access-hub'),
  ],
  platform: [
    getExecHubTab('exec-observability-hub'),
    getExecHubTab('exec-legal-update-hub'),
    getExecHubTab('exec-email-guardrail-hub'),
    getExecHubTab('exec-platform-settings-hub'),
    getExecHubTab('exec-integrations-content-hub'),
    getExecHubTab('exec-policy-compliance-hub'),
    getExecHubTab('exec-theme-globalization-hub'),
  ],
};

const HUB_NAV_ITEMS = Object.values(CATEGORY_TABS).flat();
const LEGACY_NAV_ITEMS = EXECUTIVE_PHASE_B_HUBS.flatMap((hub) => (
  hub.legacyTabs.map((legacy) => ({
    id: legacy.id,
    label: legacy.label,
    icon: legacy.icon,
    route: legacy.route,
  }))
));

const NAV_ITEMS = [
  ...HUB_NAV_ITEMS,
  ...LEGACY_NAV_ITEMS.filter((legacy) => !HUB_NAV_ITEMS.some((hub) => hub.id === legacy.id)),
];

const resolveExecutiveCategoryForSection = (sectionId: string) => {
  const normalizedRaw = EXEC_SECTION_LEGACY_ALIASES[sectionId] || sectionId;
  const normalized = EXECUTIVE_LEGACY_TAB_TO_HUB[normalizedRaw] || normalizedRaw;
  for (const [catId, tabs] of Object.entries(CATEGORY_TABS)) {
    if (tabs.some((tab) => tab.id === normalized)) {
      return catId;
    }
  }
  return 'overview';
};

const normalizeExecutiveSection = (value: string | null | undefined) => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return EXEC_SECTION_LEGACY_ALIASES[raw] || EXEC_SECTION_ALIASES_FROM_OPERATIONS[raw] || raw;
};

export default function ExecutiveDashboard() {
  if (Platform.OS !== 'web') {
    return <WebOnlyScreen featureNameKey="webOnly.executiveDashboard" featureNameFallback="Executive Dashboard" />;
  }
  const s = useExecStyles();
  const { user, loading: authLoading, logout } = useAuth();
  const {darkMode, colors} = useTheme();
  const { t } = useTranslation();
  const tx = React.useCallback((key: string, fallback: string) => {
    const v = t(key);
    return v === key ? fallback : v;
  }, [t]);

  // @autofix-moved: was module-level const CATEGORIES
  const CATEGORIES = [
    { id: 'overview', label: 'Overview', icon: 'grid', color: colors.primary },
    { id: 'growth', label: 'Growth', icon: 'trending-up', color: colors.successText },
    { id: 'hiring', label: 'Hiring', icon: 'briefcase', color: colors.accent },
    { id: 'security', label: 'Security', icon: 'shield-half', color: colors.error },
    { id: 'platform', label: 'Platform', icon: 'settings', color: colors.textMuted },
  ];
  const AC = getAdminColors(darkMode);
  const router = useRouter();
  const routeParams = useLocalSearchParams<{ section?: string | string[]; tab?: string | string[] }>();
  const { width } = useWindowDimensions();
  const hasWebLocation = Platform.OS === 'web' && typeof window !== 'undefined' && !!window.location;
  const [activeSection, setActiveSection] = useState(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || !window.location) return 'overview';
    const params = new URLSearchParams(window.location.search || '');
    const section = normalizeExecutiveSection(params.get('section') || params.get('tab'));
    if (section && NAV_ITEMS.some((item) => item.id === section)) {
      return section;
    }
    return 'overview';
  });
  const [activeCategory, setActiveCategory] = useState(() => {
    const initSection = Platform.OS === 'web' && typeof window !== 'undefined' && window.location
      ? normalizeExecutiveSection(new URLSearchParams(window.location.search || '').get('section') || new URLSearchParams(window.location.search || '').get('tab')) || 'overview'
      : 'overview';
    return resolveExecutiveCategoryForSection(initSection);
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [dashboardRecoverableError, setDashboardRecoverableError] = useState('');

  // Data states
  const [kpis, setKpis] = useState<any>(null);
  const [financial, setFinancial] = useState<any>(null);
  const [risk, setRisk] = useState<any>(null);
  const [heatmap, setHeatmap] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [userTotal, setUserTotal] = useState(0);
  const [userPages, setUserPages] = useState(1);
  const [userSearch, setUserSearch] = useState('');
  const [userPage, setUserPage] = useState(1);
  const [period, setPeriod] = useState('7d');
  const [pinnedTabs, setPinnedTabs] = useState<string[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchIndex, setSearchIndex] = useState(0);
  const searchInputRef = React.useRef<any>(null);
  const [recentlyViewed, setRecentlyViewed] = useState<string[]>([]);
  const [tabFrequency, setTabFrequency] = useState<Record<string, number>>({});
  const [idvData, setIdvData] = useState<any>(null);
  const [jobStats, setJobStats] = useState<any>(null);
  const [jobApprovals, setJobApprovals] = useState<any[]>([]);
  const [jobApprovalStats, setJobApprovalStats] = useState<any>(null);
  const [decidingId, setDecidingId] = useState('');
  const [idvOverrideLoading, setIdvOverrideLoading] = useState('');
  const [lastRefresh, setLastRefresh] = useState(new Date());
  const [lightboxAtts, setLightboxAtts] = useState<any[]>([]);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [securityScore, setSecurityScore] = useState<any>(null);
  const [shortcutSheetOpen, setShortcutSheetOpen] = useState(false);
  const [debugAdvancedMode, setDebugAdvancedMode] = useState(false);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const aliasTelemetrySeenRef = React.useRef<Record<string, boolean>>({});

  const emitAliasTelemetry = useCallback((sourceTabId: string, canonicalTabId: string, context: string) => {
    const source = String(sourceTabId || '').trim();
    const canonical = String(canonicalTabId || '').trim();
    if (!source || !canonical || source === canonical) return;
    const key = `executive:${source}->${canonical}:${context}`;
    if (aliasTelemetrySeenRef.current[key]) return;
    aliasTelemetrySeenRef.current[key] = true;
    trackTabAliasHit({
      console: 'executive',
      source_tab_id: source,
      canonical_tab_id: canonical,
      context,
    }).catch(() => {});
  }, []);

  const handleSignOutConfirmed = useCallback(async () => {
    setSigningOut(true);
    try {
      await logout();
    } catch (error) { handleAppRecoverableError({ scope: 'executive-dashboard.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSigningOut(false);
    setShowSignOutConfirm(false);
    router.replace('/auth/login?logout=1' as any);
  }, [logout, router]);

  const routeSectionParam = Array.isArray(routeParams.section) ? routeParams.section[0] : routeParams.section;
  const routeTabParam = Array.isArray(routeParams.tab) ? routeParams.tab[0] : routeParams.tab;
  useEffect(() => {
    const rawFromUrl = hasWebLocation
      ? (new URLSearchParams(window.location.search || '').get('section') || new URLSearchParams(window.location.search || '').get('tab'))
      : null;
    const rawSection = String(routeSectionParam || routeTabParam || rawFromUrl || '').trim();
    const sectionParam = normalizeExecutiveSection(rawSection);
    if (!sectionParam) return;
    if (!NAV_ITEMS.some((item) => item.id === sectionParam)) return;
    if (rawSection && rawSection !== sectionParam) {
      emitAliasTelemetry(rawSection, sectionParam, 'route_param');
    }
    if (sectionParam === activeSection) return;
    setActiveSection(sectionParam);
    setActiveCategory(resolveExecutiveCategoryForSection(sectionParam));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeSectionParam, routeTabParam, hasWebLocation, emitAliasTelemetry]);

  useEffect(() => {
    if (!hasWebLocation) return;
    try {
      const params = new URLSearchParams(window.location.search || '');
      if (params.get('section') === activeSection) return;
      params.set('section', activeSection);
      const next = `${window.location.pathname}?${params.toString()}`;
      window.history.replaceState({}, '', next);
    } catch (error) { handleAppRecoverableError({ scope: 'executive-dashboard.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [activeSection, hasWebLocation]);

  useEffect(() => {
    if (activeSection !== 'ai-analytics-link') return;
    router.push('/ai-feature-dashboard' as any);
  }, [activeSection, router]);

  // Load pinned tabs, recently viewed, and frequency
  useEffect(() => {
    (async () => {
      try {
        const [storedPins, storedRecent, storedFreq] = await Promise.all([
          AsyncStorage.getItem('exec_pinned_tabs'),
          AsyncStorage.getItem('exec_recently_viewed'),
          AsyncStorage.getItem('exec_tab_frequency'),
        ]);
        if (storedPins) {
          const parsedPins = JSON.parse(storedPins);
          const normalizedPins = Array.isArray(parsedPins)
            ? Array.from(new Set(parsedPins.map((id: string) => {
              const normalizedId = normalizeExecutiveSection(id);
              return EXECUTIVE_LEGACY_TAB_TO_HUB[normalizedId] || normalizedId;
            })))
            : [];
          setPinnedTabs(normalizedPins);
        }
        if (storedRecent) setRecentlyViewed(JSON.parse(storedRecent));
        if (storedFreq) setTabFrequency(JSON.parse(storedFreq));
      } catch (error) { handleAppRecoverableError({ scope: 'executive-dashboard.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    })();
  }, []);

  // Track recently viewed + frequency
  useEffect(() => {
    if (!activeSection || activeSection === 'overview') return;
    setRecentlyViewed(prev => {
      const next = [activeSection, ...prev.filter(t => t !== activeSection)].slice(0, 8);
      AsyncStorage.setItem('exec_recently_viewed', JSON.stringify(next)).catch(() => {});
      return next;
    });
    setTabFrequency(prev => {
      const next = { ...prev, [activeSection]: (prev[activeSection] || 0) + 1 };
      AsyncStorage.setItem('exec_tab_frequency', JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, [activeSection]);

  const clearRecentlyViewed = useCallback(() => {
    setRecentlyViewed([]);
    AsyncStorage.removeItem('exec_recently_viewed').catch(() => {});
  }, []);

  const togglePin = useCallback(async (tabId: string) => {
    setPinnedTabs(prev => {
      const next = prev.includes(tabId) ? prev.filter(t => t !== tabId) : [...prev, tabId];
      AsyncStorage.setItem('exec_pinned_tabs', JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const handleSectionSelect = useCallback((sectionId: string) => {
    const normalizedSection = normalizeExecutiveSection(sectionId);
    if (!normalizedSection || !NAV_ITEMS.some((item) => item.id === normalizedSection)) return;
    if (sectionId !== normalizedSection) {
      emitAliasTelemetry(sectionId, normalizedSection, 'section_select');
    }
    setActiveSection(normalizedSection);
    setActiveCategory(resolveExecutiveCategoryForSection(normalizedSection));
    if (hasWebLocation) {
      try {
        const params = new URLSearchParams(window.location.search || '');
        params.set('section', normalizedSection);
        const next = `${window.location.pathname}?${params.toString()}`;
        window.history.replaceState({}, '', next);
      } catch (error) { handleAppRecoverableError({ scope: 'executive-dashboard.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  }, [hasWebLocation, emitAliasTelemetry]);

  const filteredNavItems = searchQuery.trim()
    ? NAV_ITEMS.filter(n => !n.route && n.label.toLowerCase().includes(searchQuery.toLowerCase()))
    : NAV_ITEMS.filter(n => !n.route);

  // Keyboard shortcuts
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(prev => { if (!prev) { setSearchQuery(''); setSearchIndex(0); } return !prev; });
        return;
      }
      if (shortcutSheetOpen) {
        if (e.key === 'Escape' || e.key === '?') { setShortcutSheetOpen(false); return; }
        return;
      }
      if (searchOpen) {
        if (e.key === 'Escape') { setSearchOpen(false); setSearchQuery(''); setSearchIndex(0); return; }
        if (e.key === 'ArrowDown') { e.preventDefault(); setSearchIndex(prev => Math.min(prev + 1, filteredNavItems.length - 1)); return; }
        if (e.key === 'ArrowUp') { e.preventDefault(); setSearchIndex(prev => Math.max(prev - 1, 0)); return; }
        if (e.key === 'Enter' && filteredNavItems.length > 0) {
          e.preventDefault();
          const selected = filteredNavItems[searchIndex];
          if (selected) { handleSectionSelect(selected.id); setSearchOpen(false); setSearchQuery(''); setSearchIndex(0); }
        }
        return;
      }
      if (!e.metaKey && !e.ctrlKey && !e.altKey) {
        const target = e.target as HTMLElement;
        if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA') return;
        const num = parseInt(e.key);
        if (num >= 1 && num <= 9 && pinnedTabs.length >= num) { e.preventDefault(); handleSectionSelect(pinnedTabs[num - 1]); }
        if (e.key === '?') { e.preventDefault(); setShortcutSheetOpen(true); }
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [searchOpen, shortcutSheetOpen, pinnedTabs, filteredNavItems, searchIndex, handleSectionSelect]);

  useEffect(() => {
    if (searchOpen && searchInputRef.current) setTimeout(() => searchInputRef.current?.focus(), 100);
  }, [searchOpen]);

  useEffect(() => { setSearchIndex(0); }, [searchQuery]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const promises: Promise<any>[] = [api.get('/admin/executive/overview').catch(() => ({ data: null }))];
      if (activeSection === 'financial' || activeSection === 'overview') promises.push(api.get(`/admin/executive/financial-intelligence?period=${period}`).catch(() => ({ data: null })));
      if (activeSection === 'risk' || activeSection === 'overview') promises.push(api.get('/admin/executive/risk-control').catch(() => ({ data: null })));
      if (activeSection === 'overview') { promises.push(api.get('/admin/executive/global-heatmap').catch(() => ({ data: null }))); promises.push(api.get('/admin/executive/security-score').catch(() => ({ data: null }))); }
      if (activeSection === 'users') promises.push(api.get(`/admin/executive/user-management?page=${userPage}&search=${encodeURIComponent(userSearch)}`).catch(() => ({ data: null })));
      if (activeSection === 'id-checker') promises.push(api.get('/id-checker/admin/dashboard').catch(() => ({ data: null })));
      if (activeSection === 'jobs') { promises.push(api.get('/jobs/admin/stats').catch(() => ({ data: null }))); promises.push(api.get('/jobs/admin/approvals').catch(() => ({ data: null }))); }

      const results = await Promise.all(promises);
      let idx = 0;
      if (results[idx]?.data) setKpis(results[idx].data); idx++;
      if (activeSection === 'financial' || activeSection === 'overview') { if (results[idx]?.data) setFinancial(results[idx].data); idx++; }
      if (activeSection === 'risk' || activeSection === 'overview') { if (results[idx]?.data) setRisk(results[idx].data); idx++; }
      if (activeSection === 'overview') { if (results[idx]?.data) setHeatmap(results[idx].data); idx++; if (results[idx]?.data) setSecurityScore(results[idx].data); idx++; }
      if (activeSection === 'users') { if (results[idx]?.data) { setUsers(results[idx].data.users || []); setUserTotal(results[idx].data.total || 0); setUserPages(results[idx].data.pages || 1); } idx++; }
      if (activeSection === 'id-checker') { if (results[idx]?.data) setIdvData(results[idx].data); idx++; }
      if (activeSection === 'jobs') { if (results[idx]?.data) setJobStats(results[idx].data); idx++; if (results[idx]?.data) { setJobApprovals(results[idx].data.approvals || []); setJobApprovalStats(results[idx].data.stats || null); } idx++; }
      setLastRefresh(new Date());
      setDashboardRecoverableError('');
    } catch (e) {
      handleAppRecoverableError({
        scope: 'executive-dashboard.load-data',
        error: e,
        message: tx('executive.errors.dashboardLoadFailed', 'Dashboard data failed to load.'),
        setError: setDashboardRecoverableError,
        onRetry: () => { void loadData(); },
      
        notifyMode: 'dialog',
        userInitiated: true,
      });
    } finally { setLoading(false); setRefreshing(false); }
  }, [activeSection, period, userPage, userSearch]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (!user?.is_admin) return;
    const interval = setInterval(() => { loadData(); }, 30000);
    return () => clearInterval(interval);
  }, [activeSection, user?.is_admin, loadData]);

  if (authLoading) {
    return (<View style={[s.container, { justifyContent: 'center', alignItems: 'center', backgroundColor: AC.bg }]}><ActivityIndicator size="large" color={AC.primary} /><Text style={[s.kpiLabel, { marginTop: 12, color: AC.textSec }]}>{tx('executive.auth.authenticating', 'Authenticating...')}</Text></View>);
  }

  const now = new Date();
  const currentSection = activeSection;
  const canonicalCurrentSection = EXECUTIVE_LEGACY_TAB_TO_HUB[currentSection] || currentSection;
  const qrPrefillParams = hasWebLocation
    ? (() => {
      const query = new URLSearchParams(window.location.search || '');
      const result: Record<string, string> = {};
      [
        'verify_report_id',
        'verify_generated_at',
        'verify_row_count',
        'verify_total_spent',
        'verify_data_hash',
        'verify_signature',
      ].forEach((key) => {
        const value = query.get(key);
        if (value) result[key] = value;
      });
      return result;
    })()
    : {};

  const renderContent = () => {
    if (loading && !kpis) {
      return (<ExecutiveDashboardSkeleton />);
    }

    const executiveHub = getExecutiveHubById(currentSection);
    if (executiveHub) {
      if (currentSection === 'exec-revenue-billing-hub') {
        return (
          <FadeSlideIn>
            <Suspense fallback={<LazyFallback />}>
              <RevenueBillingEnterpriseWorkspace />
            </Suspense>
          </FadeSlideIn>
        );
      }
      if (currentSection === 'exec-platform-settings-hub') {
        return (
          <FadeSlideIn>
            <Suspense fallback={<LazyFallback />}>
              <PlatformSettingsEnterpriseWorkspace />
            </Suspense>
          </FadeSlideIn>
        );
      }
      if (currentSection === 'exec-legal-update-hub') {
        return (
          <FadeSlideIn>
            <Suspense fallback={<LazyFallback />}>
              <LegalUpdateEnterpriseWorkspace />
            </Suspense>
          </FadeSlideIn>
        );
      }
      if (currentSection === 'exec-email-guardrail-hub') {
        return (
          <FadeSlideIn>
            <Suspense fallback={<LazyFallback />}>
              <EmailGuardrailControlCenterWorkspace />
            </Suspense>
          </FadeSlideIn>
        );
      }
      return (
        <FadeSlideIn>
          <View style={{ gap: 12 }}>
            <TabMergeHubPanel
              colors={AC}
              hub={executiveHub}
              onOpenLegacyTab={(legacyTab) => {
                if (legacyTab.route) {
                  router.push(legacyTab.route as any);
                  return;
                }
                handleSectionSelect(legacyTab.id);
              }}
            />
          </View>
        </FadeSlideIn>
      );
    }

    return (
      <FadeSlideIn>
      <ScrollView style={s.scrollContent} contentContainerStyle={s.scrollInner}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadData(); }} tintColor={AC.primary} />}>

        <>
            {dashboardRecoverableError ? (
              <View
                style={{ marginBottom: 12, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: AC.error + '35', backgroundColor: AC.errorSoft, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
                data-testid="executive-dashboard-recoverable-error-banner"
                testID="executive-dashboard-recoverable-error-banner"
              >
                <Text style={{ color: AC.errorText, fontSize: 12, fontWeight: '700', flex: 1 }} data-testid="executive-dashboard-recoverable-error-text" testID="executive-dashboard-recoverable-error-text">{dashboardRecoverableError}</Text>
                <TouchableOpacity
                  onPress={() => { void loadData(); }}
                  style={{ backgroundColor: AC.error, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8 }}
                  data-testid="executive-dashboard-recoverable-error-retry"
                  testID="executive-dashboard-recoverable-error-retry"
                >
                  <Text style={{ color: AC.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('common.retry', 'Retry')}</Text>
                </TouchableOpacity>
              </View>
            ) : null}
            <ExecOverviewSection activeSection={currentSection} kpis={kpis} financial={financial} risk={risk} heatmap={heatmap} securityScore={securityScore} period={period} setPeriod={setPeriod} lastRefresh={lastRefresh} refreshing={refreshing} loadData={loadData} />

            {currentSection === 'users' && <ExecUserManagementPanel users={users} total={userTotal} search={userSearch} setSearch={setUserSearch} page={userPage} setPage={setUserPage} pages={userPages} />}

            {currentSection === 'jobs' && <ExecJobControlPanel jobStats={jobStats} jobApprovals={jobApprovals} jobApprovalStats={jobApprovalStats} decidingId={decidingId} setDecidingId={setDecidingId} loadData={loadData} />}

            {currentSection === 'id-checker' && <ExecIDVerificationPanel idvData={idvData} idvOverrideLoading={idvOverrideLoading} setIdvOverrideLoading={setIdvOverrideLoading} loadData={loadData} setLightboxAtts={setLightboxAtts} setLightboxOpen={setLightboxOpen} />}

            {currentSection === 'content' && <ExecContentPanel />}
            {currentSection === 'logs' && <ExecLogsPanel />}

            {/* Lazy-loaded panels */}
            {currentSection === 'security' && <View data-testid="security-dashboard-section" testID="security-dashboard-section"><Suspense fallback={<LazyFallback />}><SecurityDashboardPanel userId={user?.user_id} isAdmin={user?.is_admin} /></Suspense></View>}
            {currentSection === 'gtec' && (
              <View data-testid="gtec-section" testID="gtec-section" style={{ gap: 12 }}>
                <View data-testid="gtec-scan-v2-section" testID="gtec-scan-v2-section">
                  <GtecScanV2Panel />
                </View>
                <View data-testid="gtec-upstream-watchdog-section" testID="gtec-upstream-watchdog-section">
                  <GtecUpstreamWatchdogPanel />
                </View>
              </View>
            )}
            {currentSection === 'pdf-policy' && <View data-testid="pdf-policy-section" testID="pdf-policy-section"><Suspense fallback={<LazyFallback />}><PdfPolicyMonitorPanel /></Suspense></View>}
            {currentSection === 'compliance-digests' && <View data-testid="compliance-digests-section" testID="compliance-digests-section"><Suspense fallback={<LazyFallback />}><ComplianceDigestHubPanel /></Suspense></View>}
            {currentSection === 'coaching-tips-cms' && <View data-testid="coaching-tips-cms-section" testID="coaching-tips-cms-section"><Suspense fallback={<LazyFallback />}><PublicCoachingTipsPanel /></Suspense></View>}
            {currentSection === 'tickertape-analytics' && <View data-testid="tickertape-analytics-section" testID="tickertape-analytics-section"><Suspense fallback={<LazyFallback />}><TickertapeAnalyticsPanel /></Suspense></View>}
            {currentSection === 'theme-validation' && <View data-testid="theme-validation-section" testID="theme-validation-section"><Suspense fallback={<LazyFallback />}><ThemeValidationDashboard /></Suspense></View>}
            {currentSection === 'support-tickets' && <View data-testid="support-tickets-section" testID="support-tickets-section"><Suspense fallback={<LazyFallback />}><UnifiedSupportPanel /></Suspense></View>}
            {currentSection === 'templates' && <View data-testid="templates-section" testID="templates-section"><Suspense fallback={<LazyFallback />}><EmailTemplatesPanel colors={AC} /></Suspense></View>}
            {currentSection === 'email-coverage' && <View data-testid="email-coverage-section" testID="email-coverage-section"><Suspense fallback={<LazyFallback />}><EmailCoverageMatrixPanel /></Suspense></View>}
            {currentSection === 'feedback-heatmap' && <View data-testid="feedback-heatmap-section" testID="feedback-heatmap-section"><Suspense fallback={<LazyFallback />}><FeedbackHeatmapPanel /></Suspense></View>}
            {currentSection === 'system-monitor' && <View data-testid="system-monitor-section" testID="system-monitor-section">{SystemMonitorPanel ? <Suspense fallback={<LazyFallback />}><SystemMonitorPanel /></Suspense> : <LazyFallback />}</View>}
            {currentSection === 'sub-analytics' && <View data-testid="subscription-analytics-section" testID="subscription-analytics-section"><Suspense fallback={<LazyFallback />}><SubscriptionAnalyticsPanel /></Suspense></View>}
            {currentSection === 'employer-portal' && <View data-testid="employer-portal-section" testID="employer-portal-section"><Suspense fallback={<LazyFallback />}><EmployerPortalPanel /></Suspense></View>}
            {currentSection === 'leaderboard-mgmt' && <View data-testid="leaderboard-mgmt-section" testID="leaderboard-mgmt-section"><Suspense fallback={<LazyFallback />}><LeaderboardManagementPanel /></Suspense></View>}
            {currentSection === 'integrations-mgmt' && <View data-testid="integrations-mgmt-section" testID="integrations-mgmt-section"><Suspense fallback={<LazyFallback />}><IntegrationManagementPanel /></Suspense></View>}
            {currentSection === 'subscription-mgmt' && <View data-testid="subscription-mgmt-section" testID="subscription-mgmt-section"><Suspense fallback={<LazyFallback />}><SubscriptionPlanManagementPanel /></Suspense></View>}
            {currentSection === 'payment-billing' && <View data-testid="payment-billing-section" testID="payment-billing-section"><Suspense fallback={<LazyFallback />}><PaymentBillingPanel prefillParams={qrPrefillParams} /></Suspense></View>}
            {(currentSection === 'iap' || currentSection === 'iap-management') && <View data-testid="iap-management-section" testID="iap-management-section"><Suspense fallback={<LazyFallback />}><IAPManagementPanel /></Suspense></View>}
            {currentSection === 'unified-revenue' && <View data-testid="unified-revenue-section" testID="unified-revenue-section"><Suspense fallback={<LazyFallback />}><UnifiedRevenuePanel /></Suspense></View>}
            {currentSection === 'keyword-tracking' && <View data-testid="keyword-tracking-section" testID="keyword-tracking-section"><Suspense fallback={<LazyFallback />}><CompetitorKeywordPanel /></Suspense></View>}
            {currentSection === 'cdn-management' && <View data-testid="cdn-management-section" testID="cdn-management-section"><Suspense fallback={<LazyFallback />}><CDNManagementPanel /></Suspense></View>}
            {currentSection === 'enterprise-security' && <View data-testid="enterprise-security-section" testID="enterprise-security-section"><Suspense fallback={<LazyFallback />}><EnterpriseSecurityPanel colors={AC} /></Suspense></View>}
            {currentSection === 'automation-engine' && <View data-testid="automation-engine-section" testID="automation-engine-section"><Suspense fallback={<LazyFallback />}><AutomationEnginePanel colors={AC} /></Suspense></View>}
            {currentSection === 'platform-settings' && <View data-testid="platform-settings-section" testID="platform-settings-section"><Suspense fallback={<LazyFallback />}><PlatformSettingsEnterpriseWorkspace /></Suspense></View>}
            {currentSection === 'legal-update' && <View data-testid="legal-update-section" testID="legal-update-section"><Suspense fallback={<LazyFallback />}><LegalUpdateEnterpriseWorkspace /></Suspense></View>}
            {currentSection === 'email-guardrail-control-center' && <View data-testid="email-guardrail-control-center-section" testID="email-guardrail-control-center-section"><Suspense fallback={<LazyFallback />}><EmailGuardrailControlCenterWorkspace /></Suspense></View>}
            {currentSection === 'sessions' && <View data-testid="session-management-section" testID="session-management-section"><Suspense fallback={<LazyFallback />}><SessionManagementPanel /></Suspense></View>}
            {currentSection === 'onboarding-analytics' && <View data-testid="onboarding-analytics-section" testID="onboarding-analytics-section"><Suspense fallback={<LazyFallback />}><OnboardingAnalyticsPanel /></Suspense></View>}
            {currentSection === 'sso-analytics' && <View data-testid="sso-analytics-section" testID="sso-analytics-section"><Suspense fallback={<LazyFallback />}><SSOAnalyticsPanel /></Suspense></View>}
            {currentSection === 'csat' && <View data-testid="csat-dashboard-section" testID="csat-dashboard-section"><Suspense fallback={<LazyFallback />}><CsatDashboardPanel colors={AC} /></Suspense></View>}
            {currentSection === 'ticket-feedback' && <View data-testid="ticket-feedback-section" testID="ticket-feedback-section"><Suspense fallback={<LazyFallback />}><TicketFeedbackIntelPanel colors={AC} /></Suspense></View>}
            {(currentSection === 'newsletter-analytics' || currentSection === 'newsletter') && <View data-testid="newsletter-analytics-section" testID="newsletter-analytics-section"><Suspense fallback={<LazyFallback />}><NewsletterAnalyticsPanel colors={AC} /></Suspense></View>}
            {currentSection === 'content-studio-analytics' && <View data-testid="content-studio-analytics-section" testID="content-studio-analytics-section"><Suspense fallback={<LazyFallback />}><ContentStudioAnalyticsPanel colors={AC} /></Suspense></View>}
            {currentSection === 'conversion' && <View data-testid="conversion-analytics-section" testID="conversion-analytics-section"><Suspense fallback={<LazyFallback />}><ConversionAnalyticsPanel colors={AC} /></Suspense></View>}
            {currentSection === 'ab-testing' && <View data-testid="ab-testing-section" testID="ab-testing-section"><Suspense fallback={<LazyFallback />}><PromptABTestingPanel /></Suspense></View>}
            {currentSection === 'revenue' && <View data-testid="revenue-analytics-section" testID="revenue-analytics-section"><Suspense fallback={<LazyFallback />}><RevenuePanel colors={AC} /></Suspense></View>}
            {currentSection === 'ai-support' && <View data-testid="ai-support-section" testID="ai-support-section"><Suspense fallback={<LazyFallback />}><AIAutoSupportPanel colors={AC} /></Suspense></View>}
            {currentSection === 'fraud' && <View data-testid="fraud-detection-section" testID="fraud-detection-section"><Suspense fallback={<LazyFallback />}><FraudDetectionPanel colors={AC} /></Suspense></View>}
            {currentSection === 'siem' && <View data-testid="siem-section" testID="siem-section"><Suspense fallback={<LazyFallback />}><SIEMPanel colors={AC} /></Suspense></View>}
            {currentSection === 'sla' && <View data-testid="sla-monitor-section" testID="sla-monitor-section"><Suspense fallback={<LazyFallback />}><SLAMonitorPanel colors={AC} /></Suspense></View>}
            {(currentSection === 'otp-delivery' || currentSection === 'otp') && <View data-testid="otp-delivery-section" testID="otp-delivery-section"><Suspense fallback={<LazyFallback />}><OTPDeliveryDashboardPanel colors={AC} /></Suspense></View>}
            {currentSection === 'webhooks' && <View data-testid="webhooks-section" testID="webhooks-section"><Suspense fallback={<LazyFallback />}><WebhookEventStreamPanel colors={AC} /></Suspense></View>}
            {currentSection === 'notifications' && <View data-testid="notifications-mgmt-section" testID="notifications-mgmt-section"><Suspense fallback={<LazyFallback />}><NotificationManagementPanel colors={AC} /></Suspense></View>}
            {currentSection === 'performance' && <View data-testid="performance-section" testID="performance-section"><Suspense fallback={<LazyFallback />}><PerformanceDashboardPanel colors={AC} /></Suspense></View>}
            {currentSection === 'page-performance' && <View data-testid="page-performance-section" testID="page-performance-section"><Suspense fallback={<LazyFallback />}><PagePerformancePanel colors={AC} /></Suspense></View>}
            {currentSection === 'ai-command-center' && <View data-testid="ai-command-center-section" testID="ai-command-center-section"><Suspense fallback={<LazyFallback />}><AICommandCenterPanel colors={AC} onNavigate={(navId) => handleSectionSelect(navId)} /></Suspense></View>}
            {currentSection === 'learning-hub-autopilot' && <View data-testid="learning-hub-autopilot-section" testID="learning-hub-autopilot-section"><Suspense fallback={<LazyFallback />}><LearningHubAutopilotExecutiveWorkspace /></Suspense></View>}
            {currentSection === 'global-adaptation' && <View data-testid="global-adaptation-section" testID="global-adaptation-section"><Suspense fallback={<LazyFallback />}><GlobalAdaptationControlCenterPanel /></Suspense></View>}
            {currentSection === 'device-audit' && <View data-testid="device-audit-section" testID="device-audit-section"><Suspense fallback={<LazyFallback />}><DeviceAuditPanel /></Suspense></View>}
          </>
      </ScrollView>
      </FadeSlideIn>
    );
  };

  return (
    <AdminRouteGate returnTo="/executive-dashboard">
    <AppShell notificationScope="admin">
      <View style={[s.container, { backgroundColor: AC.bg }]} data-testid="executive-dashboard" testID="executive-dashboard">
        <Suspense fallback={null}>
          <AttachmentLightbox attachments={lightboxAtts} visible={lightboxOpen} onClose={() => { setLightboxOpen(false); setLightboxAtts([]); }} baseUrl={api.defaults.baseURL} />
        </Suspense>

        <View
          style={{
            borderBottomWidth: 0,
            paddingHorizontal: width >= 1024 ? 24 : 14,
            paddingTop: 0,
            paddingBottom: 0,
            gap: 0,
          }}
          data-testid="executive-dashboard-header"
          testID="executive-dashboard-header"
        >
          {/* ── Hero Banner ── */}
          <View style={{
            backgroundColor: colors.primary,
            borderRadius: width >= 768 ? 18 : 12,
            padding: width >= 768 ? 24 : 16,
            marginTop: width >= 768 ? 16 : 10,
            marginBottom: 12,
            ...(Platform.OS === 'web' ? { boxShadow: '0 8px 32px rgba(37,99,235,0.25)' } as any : {}),
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success }} />
                  <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1.5 }}>
                    {tx('executive.hero.live', 'Live')}
                  </Text>
                </View>
                <Text style={{ color: colors.text, fontSize: width >= 768 ? 28 : 22, fontWeight: '800', letterSpacing: -0.5 }} data-testid="executive-header-greeting" testID="executive-header-greeting">
                  {tx('executive.hero.title', 'Executive Console')}
                </Text>
                <Text style={{ color: colors.primaryText, marginTop: 4, fontSize: 13 }} data-testid="executive-header-date" testID="executive-header-date">
                  {now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })} — {tx('executive.hero.welcome', 'Welcome')}, {user?.name || tx('executive.hero.admin', 'Admin')}
                </Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="executive-header-actions" testID="executive-header-actions">
                <TouchableOpacity onPress={() => { setSearchOpen(true); setSearchQuery(''); }} data-testid="executive-search-button" testID="executive-search-button"
                  style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="search" size={18} color={colors.primaryText} />
                </TouchableOpacity>
                <TouchableOpacity onPress={loadData} data-testid="admin-refresh-button" testID="admin-refresh-button"
                  style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="refresh" size={18} color={colors.primaryText} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setShortcutSheetOpen(true)} data-testid="shortcut-sheet-trigger" testID="shortcut-sheet-trigger"
                  style={{ width: 38, height: 38, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="help-circle-outline" size={18} color={colors.primaryText} />
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setDebugAdvancedMode((prev) => !prev)}
                  data-testid="executive-debug-advanced-toggle"
                  testID="executive-debug-advanced-toggle"
                  style={{
                    height: 38,
                    borderRadius: 10,
                    backgroundColor: debugAdvancedMode ? 'rgba(245,158,11,0.22)' : 'rgba(255,255,255,0.15)',
                    alignItems: 'center',
                    justifyContent: 'center',
                    paddingHorizontal: 10,
                    flexDirection: 'row',
                    gap: 6,
                  }}
                >
                  <Ionicons name={debugAdvancedMode ? 'bug' : 'bug-outline'} size={14} color={colors.primaryText} />
                  {width >= 768 ? (
                    <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>
                      {tx('executive.header.debugAdvanced', 'Debug / Advanced')}
                    </Text>
                  ) : null}
                </TouchableOpacity>
              </View>
            </View>
          </View>

          {/* ── GTEC Global System Directive Banner ──
              Persistent on every admin page: shows directive version +
              last §12 scan status (ALWAYS-ACTIVE, required by directive §1). */}
          <GtecDirectiveBanner />

          {/* ── Category Bar ── */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 10 }} contentContainerStyle={{ gap: 6, paddingHorizontal: 2 }}>
            {pinnedTabs.length > 0 && (
              <TouchableOpacity
                onPress={() => setActiveCategory('favorites')}
                style={{
                  flexDirection: 'row', alignItems: 'center', gap: 7,
                  paddingHorizontal: 14, paddingVertical: 9,
                  borderRadius: 10, borderWidth: 1,
                  borderColor: activeCategory === 'favorites' ? colors.warningSoft : AC.border,
                  backgroundColor: activeCategory === 'favorites' ? colors.warningSoft : 'transparent',
                }}
                data-testid="exec-category-favorites"
                testID="exec-category-favorites"
              >
                <Ionicons name="star" size={15} color={activeCategory === 'favorites' ? colors.warning : AC.textSec} />
                <Text style={{ color: activeCategory === 'favorites' ? colors.warning : AC.textSec, fontSize: 12, fontWeight: activeCategory === 'favorites' ? '700' : '600' }}>
                  {tx('executive.category.favorites', 'Favorites')} ({pinnedTabs.length})
                </Text>
              </TouchableOpacity>
            )}
            {CATEGORIES.map((cat) => {
              const isActive = activeCategory === cat.id;
              return (
                <TouchableOpacity
                  key={cat.id}
                  onPress={() => {
                    setActiveCategory(cat.id);
                    const firstTab = CATEGORY_TABS[cat.id]?.find(t => !t.route);
                    if (firstTab) handleSectionSelect(firstTab.id);
                  }}
                  style={{
                    flexDirection: 'row', alignItems: 'center', gap: 7,
                    paddingHorizontal: 14, paddingVertical: 9,
                    borderRadius: 10, borderWidth: 1,
                    borderColor: isActive ? `${cat.color}60` : AC.border,
                    backgroundColor: isActive ? `${cat.color}18` : 'transparent',
                  }}
                  data-testid={`exec-category-${cat.id}`}
                  testID={`exec-category-${cat.id}`}
                >
                  <Ionicons name={cat.icon as any} size={15} color={isActive ? cat.color : AC.textSec} />
                  <Text style={{ color: isActive ? cat.color : AC.textSec, fontSize: 12, fontWeight: isActive ? '700' : '600' }}>
                    {tx(`executive.category.${cat.id}`, cat.label)}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {/* ── Subtabs for active category ── */}
          <View data-testid="executive-section-tabs" testID="executive-section-tabs">
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingHorizontal: 2, paddingBottom: 10 }}>
              {(activeCategory === 'favorites'
                ? pinnedTabs.map(id => NAV_ITEMS.find(n => n.id === id)).filter(Boolean) as typeof NAV_ITEMS
                : (CATEGORY_TABS[activeCategory] || [])
              ).map((item) => {
                if (item.route) {
                  return (
                    <TouchableOpacity
                      key={item.id}
                      onPress={() => router.push(item.route as any)}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 12, paddingVertical: 8,
                        borderRadius: 8, borderWidth: 1,
                        borderColor: 'rgba(59,130,246,0.32)',
                        backgroundColor: 'rgba(59,130,246,0.08)',
                      }}
                      data-testid={`executive-quick-link-${item.id}`}
                      testID={`executive-quick-link-${item.id}`}
                    >
                      <Ionicons name={item.icon as any} size={13} color={colors.primary} />
                      <Text style={{ color: colors.info, fontSize: 12, fontWeight: '600' }}>{tx(`executive.section.${item.id}`, item.label)}</Text>
                      <Ionicons name="open-outline" size={11} color={colors.primary} />
                    </TouchableOpacity>
                  );
                }
                const active = canonicalCurrentSection === item.id;
                const debugVersion = CONSOLE_TAB_DEBUG_VERSIONS[item.id];
                const catColor = activeCategory === 'favorites' ? colors.warning : (CATEGORIES.find(c => c.id === activeCategory)?.color || colors.primary);
                const isPinned = pinnedTabs.includes(item.id);
                return (
                  <View key={item.id} style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <TouchableOpacity
                      onPress={() => handleSectionSelect(item.id)}
                      style={{
                        flexDirection: 'row', alignItems: 'center', gap: 6,
                        paddingHorizontal: 12, paddingVertical: 8,
                        borderRadius: 8, borderTopRightRadius: 0, borderBottomRightRadius: 0,
                        borderWidth: 1, borderRightWidth: 0,
                        borderColor: active ? `${catColor}80` : AC.border,
                        backgroundColor: active ? `${catColor}20` : AC.card,
                      }}
                      data-testid={`executive-section-tab-${item.id}`}
                      testID={`executive-section-tab-${item.id}`}
                    >
                      <Ionicons name={item.icon as any} size={14} color={active ? catColor : AC.textSec} />
                      <Text style={{ color: active ? catColor : AC.textSec, fontSize: 12, fontWeight: active ? '700' : '600' }}>{tx(`executive.section.${item.id}`, item.label)}</Text>
                      {debugAdvancedMode && debugVersion ? (
                        <View
                          style={{
                            borderRadius: 999,
                            paddingHorizontal: 6,
                            paddingVertical: 2,
                            borderWidth: 1,
                            borderColor: `${catColor}66`,
                            backgroundColor: `${catColor}22`,
                          }}
                          data-testid={`executive-tab-version-badge-${item.id}`}
                          testID={`executive-tab-version-badge-${item.id}`}
                        >
                          <Text style={{ color: active ? catColor : AC.textSec, fontSize: 9, fontWeight: '800' }}>
                            {debugVersion}
                          </Text>
                        </View>
                      ) : null}
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => togglePin(item.id)}
                      style={{
                        paddingHorizontal: 8, paddingVertical: 8,
                        borderRadius: 8, borderTopLeftRadius: 0, borderBottomLeftRadius: 0,
                        borderWidth: 1, borderLeftWidth: 0,
                        borderColor: active ? `${catColor}80` : AC.border,
                        backgroundColor: active ? `${catColor}20` : AC.card,
                      }}
                      data-testid={`executive-pin-${item.id}`}
                      testID={`executive-pin-${item.id}`}
                    >
                      <Ionicons name={isPinned ? 'star' : 'star-outline'} size={12} color={isPinned ? colors.warning : AC.textMuted} />
                    </TouchableOpacity>
                  </View>
                );
              })}
            </ScrollView>
          </View>
        </View>

        <View style={{ flex: 1 }} data-testid="executive-dashboard-content" testID="executive-dashboard-content">
          {renderContent()}
        </View>

        <ExecSearchModal
          searchOpen={searchOpen} searchQuery={searchQuery} setSearchQuery={setSearchQuery}
          searchIndex={searchIndex} setSearchIndex={setSearchIndex}
          filteredNavItems={filteredNavItems} pinnedTabs={pinnedTabs}
          recentlyViewed={recentlyViewed} clearRecentlyViewed={clearRecentlyViewed}
          tabFrequency={tabFrequency} setActiveSection={handleSectionSelect}
          onClose={() => { setSearchOpen(false); setSearchQuery(''); setSearchIndex(0); }}
          navItems={NAV_ITEMS} width={width} searchInputRef={searchInputRef}
          onNavigateToDashboard={(route, tabId) => {
            router.push((tabId ? `${route}?tab=${tabId}` : route) as any);
          }}
        />

        <ExecShortcutSheet
          visible={shortcutSheetOpen}
          onClose={() => setShortcutSheetOpen(false)}
          pinnedCount={pinnedTabs.length}
        />

        <EnterpriseSignOutConfirmModal
          visible={showSignOutConfirm}
          loading={signingOut}
          onCancel={() => setShowSignOutConfirm(false)}
          onConfirm={handleSignOutConfirmed}
          darkMode={darkMode}
          testIdPrefix="executive-signout"
        />
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}
