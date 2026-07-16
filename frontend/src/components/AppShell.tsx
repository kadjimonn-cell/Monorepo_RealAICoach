import React, { useMemo, useRef, useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, useWindowDimensions, Animated, Pressable, Image, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, usePathname } from 'expo-router';
import { useActivityTracker } from '../hooks/useActivityTracker';
import { useTrackLastSidebarRoute } from '../hooks/useLastSidebarRoute';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useNavigationStore } from '../store/useNavigationStore';
import { useTranslation } from '../hooks/useTranslation';
import { useWebPush } from '../hooks/useWebPush';
import RenewalBanner from './RenewalBanner';
import SessionTimeout from './SessionTimeout';
import WelcomeBackBanner from './WelcomeBackBanner';
import StartupRecoveryBanner from './StartupRecoveryBanner';
import SubscriptionBadge from './SubscriptionBadge';
import UsageLimitIndicator from './UsageLimitIndicator';
import NotificationBell, { NotificationProvider, NotificationOverlay, useNotificationCenter } from './NotificationBell';
import GlobalNavBar from './GlobalNavBar';
import LanguageSwitcher from './LanguageSwitcher';
import TeamNotificationToasts from './TeamNotificationToasts';
import SmartOnboarding from './SmartOnboarding';
import { WhatsNewBadge } from './changelog/WhatsNewModal';
import PageFloatingBackground from './PageFloatingBackground';
import PwaInstallPrompt from './PwaInstallPrompt';
import { notificationEvents } from '../utils/notificationEvents';
import { useLocation } from '../context/LocationContext';
import api from '../services/api';
import EnterpriseSignOutConfirmModal from './auth/EnterpriseSignOutConfirmModal';
import { ProtectedRouteGate } from './auth/ProtectedRouteGate';
import { useViewportWidth } from '../hooks/useViewportWidth';
import { IDENTITY_LAYOUT } from '../constants/identityLayout';
import { handleAppRecoverableError } from '../utils/appRecoverableError';
import { hasAdminConsoleVisibility } from '../utils/adminAccess';
import { consumeSubscriptionReturnToast } from '../utils/subscriptionReturnToast';
import { BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY, MONO_FONT_FAMILY } from '../constants/appTypography';

/* ──────────────────────────────────────
   Theme Toggle — compact pill
   ────────────────────────────────────── */
function ThemeToggle() {
  const { themeMode, setThemeMode, colors } = useTheme();
  const modes: { key: 'light' | 'dark' | 'system'; icon: string; label: string }[] = [
    { key: 'light', icon: 'sunny', label: 'Light' },
    { key: 'dark', icon: 'moon', label: 'Dark' },
    { key: 'system', icon: 'desktop', label: 'System' },
  ];
  return (
    <View data-testid="theme-toggle" testID="theme-toggle" role="radiogroup" aria-label="Theme" style={{
      flexDirection: 'row', borderRadius: 8, padding: 2, gap: 1,
      backgroundColor: colors.surfaceHover,
      borderWidth: 1,
      borderColor: colors.border,
    }}>
      {modes.map(m => {
        const on = themeMode === m.key;
        return (
          <TouchableOpacity
            key={m.key}
            data-testid={`theme-toggle-${m.key}`}
            testID={`theme-toggle-${m.key}`}
            activeOpacity={0.7}
            onPress={() => setThemeMode(m.key)}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            accessibilityLabel={`${m.label} theme`}
            aria-label={`${m.label} theme`}
            aria-checked={on}
            style={{
              flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 5, borderRadius: 6,
              backgroundColor: on ? colors.primary : 'transparent',
              ...(Platform.OS === 'web' && on ? { boxShadow: '0 1px 2px rgba(0,0,0,0.08)' } as any : {}),
              ...(Platform.OS === 'web' ? { transition: 'all 0.15s ease' } as any : {}),
            }}>
            <Ionicons name={m.icon as any} size={12} color={on ? colors.primaryText : colors.textMuted} />
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

/* ──────────────────────────────────────
   Web Push Notification Prompt
   ────────────────────────────────────── */
function WebPushPrompt({ userId }: { userId?: string }) {
  const { state, subscribe } = useWebPush(userId);
  const { colors } = useTheme();
  const { t } = useTranslation();
  if (Platform.OS !== 'web' || state !== 'prompt') return null;

  return (
    <TouchableOpacity
      data-testid="web-push-enable-btn" testID="web-push-enable-btn"
      activeOpacity={0.7}
      onPress={subscribe}
      style={{
        flexDirection: 'row', alignItems: 'center', gap: 8,
        paddingVertical: 8, paddingHorizontal: 12, borderRadius: 10,
        backgroundColor: (globalThis as any).__alphaColor(colors.primary, '12'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, '30'),
      }}
    >
      <Ionicons name="notifications-outline" size={15} color={colors.primary} />
      <Text style={{ flex: 1, fontSize: 12, fontWeight: '600', color: colors.primary }}>
        {t('nav.enableNotifications')}
      </Text>
      <Ionicons name="chevron-forward" size={12} color={colors.primary} />
    </TouchableOpacity>
  );
}

/* ──────────────────────────────────────
   LOCKED NAVIGATION — Do NOT add/remove items
   ────────────────────────────────────── */
export const BASE_NAV_ITEMS = [
  { key: '_section_main', label: 'MAIN', section: true },
  { key: 'home', label: 'Dashboard', icon: 'grid-outline', href: '/dashboard' },
  { key: '_section_platform', label: 'PLATFORM', section: true },
  { key: 'ai-gallery', label: 'AI Feature Gallery', icon: 'sparkles-outline', href: '/feature-gallery' },
  { key: 'games-station', label: 'FPS Game', icon: 'locate-outline', href: '/features/fps-game' },
  { key: 'flappy-bird', label: 'Flappy Bird Game', icon: 'paper-plane-outline', href: '/features/flappy-bird' },
  { key: 'watch-videos', label: 'Watch Videos', icon: 'film-outline', href: '/features/watch-videos' },
  { key: 'audio-studio', label: 'Audio Studio', icon: 'musical-notes-outline', href: '/features/audio-studio' },
  { key: 'my-podcasts', label: 'My Podcasts', icon: 'mic-outline', href: '/features/my-podcasts' },
  { key: 'sports', label: 'Sports', icon: 'american-football-outline', href: '/features/sports' },
  { key: 'travel-visa', label: 'Travel Visa', icon: 'airplane-outline', href: '/features/travel-visa' },
  { key: 'daily-meditation', label: 'Daily Meditation', icon: 'leaf-outline', href: '/features/daily-meditation' },
  { key: '_section_ai_tools', label: 'AI TOOLS', section: true },
  { key: 'ai-learning-hub', label: 'Learning Hub', icon: 'school-outline', href: '/ai-learning-hub' },
  { key: 'ai-coaching-team', label: 'AI Coaching Team', icon: 'people-circle-outline', href: '/ai-coaching-team' },
  { key: 'ai-briefing', label: 'Daily Briefing', icon: 'newspaper-outline', href: '/ai-briefing' },
  { key: 'library', label: 'Library', icon: 'book-outline', href: '/content-library' },
  { key: 'book-meeting', label: 'My Agenda', icon: 'calendar-outline', href: '/book-meeting' },
  { key: 'integrations', label: 'Integrations', icon: 'git-network-outline', href: '/integrations' },
  { key: '_section_insights', label: 'INSIGHTS', section: true },
  { key: 'my-analytics', label: 'My Analytics', icon: 'bar-chart-outline', href: '/my-analytics' },
  { key: 'leaderboard', label: 'Leaderboard', icon: 'podium-outline', href: '/leaderboard' },
  { key: 'notifications', label: 'Notifications', icon: 'notifications-outline', href: '/notifications' },
  { key: 'progress', label: 'Progress', icon: 'trending-up-outline', href: '/progress' },
  { key: 'certificate-gallery', label: 'Certificates', icon: 'ribbon-outline', href: '/certificate-gallery' },
  { key: '_section_hiring', label: 'HIRING', section: true },
  { key: 'jobs-portal', label: 'Job Search', icon: 'search-outline', href: '/job-search' },
  { key: 'referrals', label: 'Referral Program', icon: 'gift-outline', href: '/referrals' },
  { key: '_section_verification', label: 'VERIFICATION', section: true },
  { key: 'id-checker', label: 'ID Checker', icon: 'finger-print-outline', href: '/id-checker' },
  { key: '_section_billing', label: 'BILLING', section: true },
  { key: 'subscription-plans', label: 'Subscription Plans', icon: 'card-outline', href: '/subscription/plans' },
  { key: 'mobile-subscriptions', label: 'In-App Purchases', icon: 'phone-portrait-outline', href: '/subscription/mobile' },
  { key: 'payment-history', label: 'Payment History', icon: 'receipt-outline', href: '/payment-history' },
  { key: '_section_support', label: 'SUPPORT', section: true },
  { key: 'help', label: 'Help & Support', icon: 'help-buoy-outline', href: '/help' },
  { key: 'nova-curation-hub', label: 'Pinned & Favorites', icon: 'bookmark-outline', href: '/nova-curation-hub' },
  { key: 'my-tickets', label: 'My Tickets', icon: 'receipt-outline', href: '/my-tickets' },
  { key: '_section_account', label: 'ACCOUNT', section: true },
  { key: 'settings', label: 'Settings', icon: 'settings-outline', href: '/settings?section=novaAssistant' },
  { key: 'profile', label: 'Profile', icon: 'person-outline', href: '/profile' },
  { key: 'logout', label: 'Log Out', icon: 'log-out-outline', href: '/logout', danger: true },
];

const ADMIN_ITEM = { key: 'admin', label: 'Executive Console', icon: 'shield-checkmark-outline', href: '/executive-dashboard' };
const ADMIN_CONSOLE_ITEM = { key: 'admin-console', label: 'Operations Console', icon: 'grid-outline', href: '/admin-console?category=people&tab=career-applications' };

// Navigation lock guardrails — additions/modifications must be explicitly approved.
const LOCKED_USER_NAV_KEYS = new Set([
  '_section_main', 'home', '_section_platform', 'ai-gallery', 'games-station', 'flappy-bird', 'watch-videos', 'audio-studio', 'my-podcasts', 'sports', 'travel-visa', 'daily-meditation',
  '_section_ai_tools', 'ai-learning-hub', 'ai-coaching-team', 'ai-briefing', 'library', 'book-meeting', 'integrations',
  '_section_insights', 'my-analytics', 'leaderboard', 'notifications', 'progress', 'certificate-gallery',
  '_section_hiring', 'jobs-portal', 'referrals',
  '_section_verification', 'id-checker',
  '_section_billing', 'subscription-plans', 'mobile-subscriptions', 'payment-history',
  '_section_support', 'help', 'nova-curation-hub', 'my-tickets',
  '_section_account', 'settings', 'profile', 'logout',
]);
const LOCKED_USER_NAV_ORDER = Object.freeze([
  '_section_main', 'home', '_section_platform', 'ai-gallery', 'games-station', 'flappy-bird', 'watch-videos', 'audio-studio', 'my-podcasts', 'sports', 'travel-visa', 'daily-meditation',
  '_section_ai_tools', 'ai-learning-hub', 'ai-coaching-team', 'ai-briefing', 'library', 'book-meeting', 'integrations',
  '_section_insights', 'my-analytics', 'leaderboard', 'notifications', 'progress', 'certificate-gallery',
  '_section_hiring', 'jobs-portal', 'referrals',
  '_section_verification', 'id-checker',
  '_section_billing', 'subscription-plans', 'mobile-subscriptions', 'payment-history',
  '_section_support', 'help', 'nova-curation-hub', 'my-tickets',
  '_section_account', 'settings', 'profile', 'logout',
]);
const LOCKED_ADMIN_NAV_KEYS = new Set(['team-management', 'admin', 'admin-console']);
const LOCKED_ADMIN_NAV_ORDER = Object.freeze(['team-management', 'admin', 'admin-console']);

export const NAV_TKEY: Record<string, string> = {
  '_section_main': 'nav.section.main',
  home: 'nav.home', 'ai-gallery': 'nav.features', 'ai-learning-hub': 'nav.learningHub',
  'ai-coaching-team': 'nav.coachingTeam', 'ai-briefing': 'nav.dailyBriefing',
  'games-station': 'nav.fpsGame', 'flappy-bird': 'nav.flappyBird', 'watch-videos': 'nav.watchVideos',
  'audio-studio': 'nav.audioStudio', 'my-podcasts': 'nav.myPodcasts',
  sports: 'nav.sports', 'travel-visa': 'nav.travelVisa', 'daily-meditation': 'nav.dailyMeditation',
  library: 'nav.library', 'book-meeting': 'nav.myAgenda', integrations: 'nav.integrations',
  'my-analytics': 'nav.myAnalytics', leaderboard: 'nav.leaderboard',
  notifications: 'nav.notifications', progress: 'nav.progress', 'certificate-gallery': 'nav.certificates',
  'jobs-portal': 'nav.jobSearch', referrals: 'nav.referralProgram',
  'id-checker': 'nav.idVerification', 'subscription-plans': 'nav.subscriptionPlans',
  'mobile-subscriptions': 'nav.mobileSubscriptions', 'payment-history': 'nav.paymentHistory',
  help: 'nav.helpSupport', 'nova-curation-hub': 'nav.novaCurationHub', 'my-tickets': 'nav.myTickets',
  settings: 'nav.settings', profile: 'nav.profile', logout: 'nav.logout',
  admin: 'nav.executiveConsole', 'team-management': 'nav.teamManagement', 'admin-console': 'nav.operationsConsole',
  '_section_platform': 'nav.section.platform', '_section_ai_tools': 'nav.section.aiTools',
  '_section_insights': 'nav.section.insights', '_section_hiring': 'nav.section.hiring',
  '_section_verification': 'nav.section.verification', '_section_billing': 'nav.section.billing',
  '_section_support': 'nav.section.support', '_section_account': 'nav.section.account',
  '_section_admin': 'nav.section.admin',
};

export const HEADER_ACTION_SNAPSHOT = {
  desktopGap: 10,
  mobileGap: 8,
};

/* ──────────────────────────────────────
   Mobile Back/Forward
   ────────────────────────────────────── */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function MobileNavButtons({ colors }: { colors: any }) {
  const { canGoBack, canGoForward, goBack, goForward } = useNavigationStore();
  return (
    <>
      <TouchableOpacity onPress={goBack} disabled={!canGoBack} data-testid="mobile-back-btn" testID="mobile-back-btn" accessibilityLabel="Go back"
        style={{ width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', opacity: canGoBack ? 1 : 0.3 }}>
        <Ionicons name="chevron-back" size={17} color={colors.text} />
      </TouchableOpacity>
      <TouchableOpacity onPress={goForward} disabled={!canGoForward} data-testid="mobile-forward-btn" testID="mobile-forward-btn" accessibilityLabel="Go forward"
        style={{ width: 32, height: 32, borderRadius: 8, alignItems: 'center', justifyContent: 'center', opacity: canGoForward ? 1 : 0.3 }}>
        <Ionicons name="chevron-forward" size={17} color={colors.text} />
      </TouchableOpacity>
    </>
  );
}

/* ──────────────────────────────────────
   Sidebar User Card — Enterprise V2
   ────────────────────────────────────── */
function UserCard({ user, compact }: { user: any; compact?: boolean }) {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  if (!user) return null;
  const layout = compact ? IDENTITY_LAYOUT.userCard.compact : IDENTITY_LAYOUT.userCard.regular;
  const initial = (user.name || user.email || '?')[0].toUpperCase();
  return (
    <View style={{
      flexDirection: 'row', alignItems: 'center', gap: layout.gap,
      paddingHorizontal: layout.paddingX, paddingVertical: layout.paddingY,
      borderRadius: compact ? 14 : 16,
      backgroundColor: compact ? colors.surface : colors.primarySoft,
      borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.primary, compact ? '14' : '18'),
      ...(Platform.OS === 'web' ? { transition: 'all 0.2s ease', cursor: 'default' } as any : {}),
    }} data-testid="sidebar-user-badge" testID="sidebar-user-badge">
      <View style={{
        width: layout.avatarSize,
        height: layout.avatarSize,
        borderRadius: layout.avatarRadius,
        overflow: 'hidden' as const,
        backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'),
        alignItems: 'center', justifyContent: 'center',
        borderWidth: 1.5, borderColor: (globalThis as any).__alphaColor(colors.primary, '30'),
      }}>
        {user.profile_image ? (
          Platform.OS === 'web' ? (
            <img src={user.profile_image} style={{ width: layout.avatarSize, height: layout.avatarSize, borderRadius: layout.avatarRadius, objectFit: 'cover' } as any} alt="" />
          ) : (
            <Image source={{ uri: user.profile_image }} style={{ width: layout.avatarSize, height: layout.avatarSize, borderRadius: layout.avatarRadius }} accessibilityLabel="profile" />
          )
        ) : (
          <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>{initial}</Text>
        )}
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, minWidth: 0 }}>
          <Text style={{ fontSize: 13, fontWeight: '800', color: colors.text, letterSpacing: -0.3, fontFamily: BODY_FONT_FAMILY, flexShrink: 1 }} numberOfLines={1}>{user.name || user.email}</Text>
          {user.kyc_verified ? (
            <View
              style={{ flexDirection: 'row', alignItems: 'center', gap: 2, borderRadius: 999, paddingHorizontal: 5, paddingVertical: 1.5, backgroundColor: (globalThis as any).__alphaColor(colors.success, '16'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(colors.success, '30') }}
              data-testid="sidebar-verified-badge" testID="sidebar-verified-badge"
              {...(Platform.OS === 'web' ? { title: tx('idChecker.badge.verified', 'Verified') } : {})}
            >
              <Ionicons name="shield-checkmark" size={9} color={colors.success} />
              <Text style={{ fontSize: 8.5, fontWeight: '800', color: colors.success }}>{tx('idChecker.badge.verified', 'Verified')}</Text>
            </View>
          ) : null}
        </View>
        <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 2, fontFamily: BODY_FONT_FAMILY }} numberOfLines={1}>{user.email}</Text>
      </View>
      <SubscriptionBadge plan={user.subscription_plan || 'free'} size="sm" isAdmin={Boolean(user.is_admin)} compact={Boolean(compact)} />
    </View>
  );
}

function NotificationNavBadge({ testId }: { testId: string }) {
  const { unread } = useNotificationCenter();
  const { colors } = useTheme();
  if (!unread) return null;
  const label = unread > 99 ? '99+' : String(unread);
  return (
    <View style={{ minWidth: 22, height: 22, borderRadius: 999, paddingHorizontal: 6, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary }} data-testid={testId} testID={testId}>
      <Text style={{ color: colors.primaryText, fontSize: 10, fontWeight: '800' }}>{label}</Text>
    </View>
  );
}

/* ──────────────────────────────────────
   Main Shell
   ────────────────────────────────────── */
type AppShellProps = {
  children: React.ReactNode;
  notificationScope?: 'user' | 'admin';
};

export default function AppShell({ children, notificationScope }: AppShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { darkMode, colors } = useTheme();
  const { user, logout, isAuthenticated, loading: authLoading } = useAuth();
  const { detectedLocale } = useLocation();
  const { width: rnWidth } = useWindowDimensions();
  const viewportWidth = useViewportWidth();
  const width = Platform.OS === 'web' ? viewportWidth : rnWidth;
  const { t, tx } = useTranslation();
  const isWide = width >= 1024;
  const isTablet = width >= 768 && width < 1024;
  const isUltraCompactMobile = width < 360;
  const isCompactMobile = width < 420;
  const mobileBrandFontSize = isTablet ? 15 : isUltraCompactMobile ? 12 : isCompactMobile ? 13 : 14;
  const isAdmin = hasAdminConsoleVisibility(user);

  useEffect(() => {
    if (!isAuthenticated || !pathname) return;
    if (isAdmin) return;

    const blockedPrefixes = [
      '/admin',
      '/admin-console',
      '/executive-dashboard',
      '/team-management',
      '/admin-system',
      '/admin-activity-log',
      '/email-templates-admin',
    ];
    const isBlocked = blockedPrefixes.some((prefix) => pathname.startsWith(prefix));
    if (!isBlocked) return;

    router.replace('/dashboard' as any);
  }, [isAuthenticated, isAdmin, pathname, router]);

  const [deferNonCriticalReady, setDeferNonCriticalReady] = useState(true);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [decorativeBackgroundReady, setDecorativeBackgroundReady] = useState(Platform.OS !== 'web');
  const [whatsNewVisible, setWhatsNewVisible] = useState(false);
  const isPaymentFlowRoute = useMemo(() => {
    const current = String(pathname || '');
    if (!current) return false;
    return [
      '/subscription/plans',
      '/subscription/payment',
      '/subscription/mobile-money',
      '/subscription/success',
      '/subscription/payment-result',
    ].some((prefix) => current.startsWith(prefix));
  }, [pathname]);

  const showNonCriticalBanners = deferNonCriticalReady && !isPaymentFlowRoute;
  const showMobileTopWhatsNew = isAuthenticated && deferNonCriticalReady && !isUltraCompactMobile;
  const showDrawerWhatsNewShortcut = isAuthenticated && deferNonCriticalReady && isUltraCompactMobile;
  const prefetchScheduledRef = useRef(false);

  // Global responsive sidebar sizing tokens (v2): prevent oversized drawers on small devices.
  const mobileDrawerWidth = useMemo(() => {
    if (isTablet) {
      // Tablet drawer should leave substantial context visible.
      return Math.min(360, Math.max(300, Math.round(width * 0.38)));
    }
    // Mobile drawer target ~70% viewport with safe clamps.
    return Math.min(300, Math.max(224, Math.round(width * 0.70)));
  }, [isTablet, width]);

  // Collapsible sidebar state (desktop only, persisted in localStorage)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      return window.localStorage.getItem('sidebar-collapsed') === '1';
    }
    return false;
  });
  // Remember the current sidebar route so a browser refresh from any
  // inside-page (or opening a new tab to `/`) lands the user back
  // exactly where they were instead of the Home dashboard. Scope rules
  // live in the hook itself (`/src/hooks/useLastSidebarRoute.ts`).
  useTrackLastSidebarRoute();
  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.localStorage.setItem('sidebar-collapsed', next ? '1' : '0');
      }
      return next;
    });
  }, []);
  const SIDEBAR_EXPANDED = width >= 1600 ? 272 : 256;
  const SIDEBAR_COLLAPSED = 64;
  const SIDEBAR_THEME_CACHE_VERSION = '2026-04-12-v3';

  const sidebarPalette = useMemo(() => {
    // v7 global token-driven palette. Sidebar now fully adapts to dark/light mode
    // via useTheme().colors — no more frozen hex values.
    if (darkMode) {
      return {
        shellBg: colors.bg,                        // v7 warm near-black
        shellBorder: colors.border,
        divider: colors.border,
        sectionText: colors.textMuted,
        itemBgActive: colors.primarySoft,           // v7 indigo tint
        itemBorderActive: colors.primary + '4D',    // ~30% indigo
        itemIconActive: colors.primary,             // v2 brand teal
        itemTextActive: colors.text,
        itemIconIdle: colors.textMuted,
        itemTextIdle: colors.textSec,
        chipBg: colors.primarySoft,
        chipBorder: colors.primary + '33',
        chipText: colors.primary,
        headerControlBg: colors.surface,
        headerControlIcon: colors.textMuted,
        avatarBg: colors.surface,
        avatarBorder: colors.border,
      };
    }
    return {
      shellBg: colors.bg,                          // v7 light: soft off-white
      shellBorder: colors.border,
      divider: colors.border,
      sectionText: colors.textMuted,
      itemBgActive: colors.primarySoft,             // v7 indigo tint (light)
      itemBorderActive: colors.primary + '33',
      itemIconActive: colors.primary,
      itemTextActive: colors.primary,
      itemIconIdle: colors.textMuted,
      itemTextIdle: colors.textSec,
      chipBg: colors.cardMuted,
      chipBorder: colors.border,
      chipText: colors.textSec,
      headerControlBg: colors.cardMuted,
      headerControlIcon: colors.textMuted,
      avatarBg: colors.cardMuted,
      avatarBorder: colors.border,
    };
  }, [darkMode, colors]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const current = window.localStorage.getItem('sidebar-theme-cache-version');
    if (current === SIDEBAR_THEME_CACHE_VERSION) return;
    window.localStorage.removeItem('sidebar-collapsed');
    window.localStorage.setItem('sidebar-theme-cache-version', SIDEBAR_THEME_CACHE_VERSION);
  }, []);

  const resolvedNotificationScope = useMemo<'user' | 'admin'>(() => {
    if (notificationScope) return notificationScope;
    const adminPaths = ['/admin-console', '/team-management', '/admin-system', '/admin-activity-log', '/email-templates-admin', '/admin/sports-source-health', '/admin/matchday-reminders', '/admin/content-integrity'];
    return adminPaths.some((path) => pathname === path || pathname.startsWith(`${path}/`)) ? 'admin' : 'user';
  }, [notificationScope, pathname]);

  const adminNavDefinitions = useMemo(() => {
    const raw = [
      { key: 'team-management', label: 'Team Management', icon: 'people-circle-outline', href: '/team-management', permission: 'employee.manage_access' },
      { ...ADMIN_ITEM, permission: 'employee.manage_operations' },
      { ...ADMIN_CONSOLE_ITEM, permission: 'employee.manage_operations' },
    ].filter((item) => LOCKED_ADMIN_NAV_KEYS.has(item.key));

    // Enforce permanent sidebar lock: only approved keys in approved order can render.
    return LOCKED_ADMIN_NAV_ORDER
      .map((lockedKey) => raw.find((item) => item.key === lockedKey))
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
  }, []);

  const allowedAdminNavItems = useMemo(() => {
    if (!isAdmin) return [];
    return adminNavDefinitions;
  }, [isAdmin, adminNavDefinitions]);

  useEffect(() => {
    // Keep header actions immediately available to avoid flaky interaction states in auth/CI flows.
    setDeferNonCriticalReady(true);
  }, [isAuthenticated, pathname]);

  useEffect(() => {
    if (Platform.OS !== 'web') {
      setDecorativeBackgroundReady(true);
      return;
    }

    let cancelled = false;
    setDecorativeBackgroundReady(false);

    const revealBackground = () => {
      if (!cancelled) setDecorativeBackgroundReady(true);
    };

    const handle =
      typeof window !== 'undefined' && 'requestIdleCallback' in window
        ? (window as any).requestIdleCallback(revealBackground, { timeout: 1400 })
        : setTimeout(revealBackground, 320);

    return () => {
      cancelled = true;
      if (typeof window !== 'undefined' && 'cancelIdleCallback' in window && typeof handle !== 'number') {
        (window as any).cancelIdleCallback(handle);
      }
      if (typeof handle === 'number') clearTimeout(handle);
    };
  }, [pathname]);

  useEffect(() => {
    if (!isAuthenticated) return;
    let mounted = true;
    (async () => {
      try {
        const res = await api.get('/i18n/language-guidance');
        const payload = res.data || {};
        if (!mounted || !payload.show) return;
        const dedupeKey = `lang-guidance-toast-${payload.preferred_language}-${payload.expected_language}`;
        if (typeof window !== 'undefined' && window.sessionStorage.getItem(dedupeKey)) return;
        notificationEvents.emit('toast', {
          id: `lang-guidance-${Date.now()}`,
          title: payload.guidance?.title || 'Language guidance available',
          message: payload.guidance?.message || `A better language match was detected for your region (${detectedLocale}).`,
          level: 'info',
        });
        api.post('/i18n/language-guidance/event', {
          event_type: 'open',
          source: 'in_app_toast',
          country: payload.country,
          metadata: {
            preferred_language: payload.preferred_language,
            expected_language: payload.expected_language,
          },
        }).catch(() => {});
        if (typeof window !== 'undefined') {
          window.sessionStorage.setItem(dedupeKey, '1');
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/AppShell.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    })();
    return () => { mounted = false; };
  }, [isAuthenticated, detectedLocale]);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (typeof window === 'undefined') return;
    const payload = consumeSubscriptionReturnToast();
    if (!payload) return;
    const normalizedCurrent = String(pathname || '').split(/[?#]/)[0] || '/';
    const normalizedTarget = String(payload.returnTarget || '').split(/[?#]/)[0] || '/';
    if (normalizedCurrent !== normalizedTarget) return;
    const localizedDestination = payload.destinationLabelKey
      ? tx(payload.destinationLabelKey, payload.destinationLabelFallback || payload.destinationLabel)
      : payload.destinationLabel;
    const localizedTitle = payload.toastTitleKey
      ? tx(payload.toastTitleKey, payload.toastTitleFallback || (payload.planName ? `${String(payload.planName).toUpperCase()} unlocked` : 'Upgrade complete')).replace('{plan}', String(payload.planName || '').toUpperCase())
      : (payload.toastTitleFallback || (payload.planName ? `${String(payload.planName).toUpperCase()} unlocked` : 'Upgrade complete'));
    const localizedMessage = payload.toastMessageKey
      ? tx(payload.toastMessageKey, payload.toastMessageFallback || `You’re back in ${localizedDestination}. Your access is ready.`).replace('{destination}', localizedDestination)
      : (payload.toastMessageFallback || `You’re back in ${localizedDestination}. Your access is ready.`);
    const localizedActionLabel = payload.actionLabelKey
      ? tx(payload.actionLabelKey, payload.actionLabelFallback || payload.actionLabel || 'View details')
      : (payload.actionLabelFallback || payload.actionLabel || undefined);
    notificationEvents.emit('toast', {
      title: localizedTitle,
      message: localizedMessage,
      type: 'success',
      actionLabel: localizedActionLabel,
      actionRoute: payload.actionRoute || undefined,
    });
  }, [isAuthenticated, pathname, tx]);

  // What's New — modal is now rendered at root _layout.tsx level via WhatsNewRootPortal.
  // AppShell only needs to pass trigger callbacks to WhatsNewBadge.
  const handleWhatsNewAutoOpen = useCallback(() => {
    notificationEvents.openWhatsNew();
  }, []);

  // Legacy: keep global __openWhatsNew for any external callers
  useEffect(() => {
    if (Platform.OS === 'web') {
      (window as any).__openWhatsNew = () => notificationEvents.openWhatsNew();
    }
    return () => {
      if (Platform.OS === 'web') {
        delete (window as any).__openWhatsNew;
      }
    };
  }, []);

  useEffect(() => {
    const unsubscribe = notificationEvents.on('whats-new-visibility', (visible) => {
      setWhatsNewVisible(Boolean(visible));
    });
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const ne = (window as any).__notificationEvents;
      setWhatsNewVisible(Boolean(ne?.whatsNewVisible));
    }
    return unsubscribe;
  }, []);

  const canTrackAdminActivity = useMemo(
    () => Boolean(isAdmin),
    [isAdmin]
  );

  // Activity tracking — auto-logs page views on route changes
  useActivityTracker(pathname, canTrackAdminActivity);

  // Admin-only keys — hidden from non-admin users regardless of where they appear
  const ADMIN_ONLY_KEYS = useMemo(() => new Set([
    'team-management',
    'admin',
    'admin-console',
    '_section_admin',
  ]), []);

  const navItems = useMemo(() => {
    // Permanent sidebar lock: only approved locked keys in approved order can render.
    const items = LOCKED_USER_NAV_ORDER
      .map((lockedKey) => BASE_NAV_ITEMS.find((item) => item.key === lockedKey))
      .filter((item): item is NonNullable<typeof item> => Boolean(item))
      .filter((item) => LOCKED_USER_NAV_KEYS.has(item.key) && !ADMIN_ONLY_KEYS.has(item.key));
    if (allowedAdminNavItems.length > 0) {
      const accountIdx = items.findIndex(i => i.key === '_section_account');
      const adminSection = [{ key: '_section_admin', label: 'ADMIN', section: true }, ...allowedAdminNavItems];
      items.splice(accountIdx, 0, ...adminSection);
    }
    return items.filter((item) => {
      if (isAdmin) return true;
      const target = String(item?.href || '');
      return !target.includes('/admin-console');
    });
  }, [allowedAdminNavItems, ADMIN_ONLY_KEYS, isAdmin]);

  useEffect(() => {
    if (!user?.user_id || typeof (router as any).prefetch !== 'function') return;
    if (prefetchScheduledRef.current) return;

    if (typeof window !== 'undefined') {
      try {
        const key = `appshell:prefetch:done:${user.user_id}`;
        if (window.sessionStorage.getItem(key) === '1') {
          prefetchScheduledRef.current = true;
          return;
        }
        window.sessionStorage.setItem(key, '1');
      } catch {
        // no-op
      }
    }

    prefetchScheduledRef.current = true;

    const lightweightTargets = ['/dashboard', '/feature-gallery'];
    const schedule = typeof window !== 'undefined' && 'requestIdleCallback' in window
      ? (cb: () => void) => (window as any).requestIdleCallback(cb, { timeout: 1800 })
      : (cb: () => void) => setTimeout(cb, 1200);

    const handle = schedule(() => {
      lightweightTargets.forEach((route) => {
        try {
          (router as any).prefetch(route);
        } catch (error) { handleAppRecoverableError({ scope: 'src/components/AppShell.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
      });
    });

    return () => {
      if (typeof window !== 'undefined' && 'cancelIdleCallback' in window && typeof handle !== 'number') {
        (window as any).cancelIdleCallback(handle);
      }
      if (typeof handle === 'number') clearTimeout(handle);
    };
  }, [user?.user_id, router]);

  const getActiveKey = () => {
    if (!pathname) return 'home';
    if (pathname.includes('job-search')) return 'jobs-portal';
    if (pathname.includes('job-platform')) return 'jobs-portal';
    if (pathname.includes('employer-apply')) return 'jobs-portal';
    if (pathname.includes('id-checker') || pathname.includes('id-verification')) return 'id-checker';
    if (pathname.includes('security')) return 'security';
    if (pathname.includes('subscription/mobile')) return 'mobile-subscriptions';
    if (pathname.includes('subscription') || pathname.includes('plans')) return 'subscription-plans';
    if (pathname.includes('payment-history')) return 'payment-history';
    if (pathname.includes('my-tickets')) return 'my-tickets';
    if (pathname.includes('nova-curation-hub')) return 'nova-curation-hub';
    if (pathname.includes('help')) return 'help';
    if (pathname.includes('ai-learning-hub')) return 'ai-learning-hub';
    if (pathname.includes('ai-coaching-team')) return 'ai-coaching-team';
    if (pathname.includes('ai-briefing')) return 'ai-briefing';
    if (pathname.includes('features/audio-studio')) return 'audio-studio';
    if (pathname.includes('features/my-podcasts')) return 'my-podcasts';
    if (pathname.includes('features/sports')) return 'sports';
    if (pathname.includes('features/fps-game')) return 'games-station';
    if (pathname.includes('features/flappy-bird')) return 'flappy-bird';
    if (pathname.includes('watch-videos')) return 'watch-videos';
    if (pathname.includes('mini-apps')) return 'features';
    if (pathname.includes('features')) return 'features';
    if (pathname.includes('analytics')) return 'my-analytics';
    if (pathname.includes('leaderboard')) return 'leaderboard';
    if (pathname.includes('notifications')) return 'notifications';
    if (pathname.includes('certificate-gallery')) return 'certificate-gallery';
    if (pathname.includes('certificate-operations')) return 'certificate-gallery';
    if (pathname.includes('ai-feature-dashboard')) return 'admin';
    if (pathname.includes('performance-observability') || pathname.includes('ops-performance')) return 'admin';
    if (pathname.includes('route-health-report') || pathname.includes('ops-route-health')) return 'admin';
    if (pathname.includes('policy-console')) return 'admin';
    if (pathname.includes('admin-system') || pathname.includes('admin-activity-log')) return 'admin';
    if (pathname.includes('admin/sports-source-health')) return 'admin-console';
    if (pathname.includes('admin/matchday-reminders')) return 'admin-console';
    if (pathname.includes('admin/content-integrity')) return 'admin-console';
    if (pathname.includes('admin/observability-center') || pathname.includes('admin/observability-proof')) return 'admin-console';
    if (pathname.includes('executive-dashboard')) return 'admin';
    if (pathname.includes('achievements')) return 'achievements';
    if (pathname.includes('messages')) return 'messages';
    if (pathname.includes('calendar')) return 'calendar';
    if (pathname.includes('job-platform')) return 'jobs-portal';
    if (pathname.includes('career')) return 'jobs-portal';
    if (pathname.includes('hiring-hub')) return 'jobs-portal';
    if (pathname.includes('employer')) return 'jobs-portal';
    if (pathname.includes('practice')) return 'jobs-portal';
    if (pathname.includes('team-management')) return 'team-management';
    if (pathname.includes('integrations')) return 'integrations';
    if (pathname.includes('book-meeting') || pathname.includes('calendar')) return 'book-meeting';
    if (pathname.includes('progress')) return 'progress';
    if (pathname.includes('feature-gallery') || pathname.includes('features/') || pathname.includes('mini-apps')) return 'ai-gallery';
    if (pathname.includes('ai-coaching-team')) return 'ai-solver';
    if (pathname.includes('ai-learning-hub')) return 'ai-learn';
    if (pathname.includes('global-ai-marketplace')) return 'ai-marketplace';
    if (pathname.includes('admin-console')) return 'admin-console';
    if (pathname.includes('admin/sports-source-health')) return 'admin-console';
    if (pathname.includes('executive-dashboard')) return 'admin';
    if (pathname.includes('my-analytics')) return 'my-analytics';
    if (pathname.includes('leaderboard')) return 'leaderboard';
    if (pathname.includes('help') || pathname.includes('faq')) return 'help';
    if (pathname.includes('my-tickets')) return 'my-tickets';
    if (pathname.includes('messages')) return 'messages';
    if (pathname.includes('settings')) return 'settings';
    if (pathname.includes('notifications')) return 'notifications';
    if (pathname.includes('content-library')) return 'library';
    if (pathname.includes('profile')) return 'profile';
    return 'home';
  };

  const activeKey = getActiveKey();

  // Map active page to background image collection variant
  const getBgVariant = (): 'home' | 'coaching' | 'admin' | 'profile' | 'gallery' | 'analytics' | 'finance' | 'productivity' | 'security' | 'default' => {
    if (activeKey === 'home') return 'home';
    if (isAdmin && (['admin', 'executive-dashboard'].includes(activeKey) || pathname.includes('admin'))) return 'admin';
    if (['profile', 'settings', 'security', 'help', 'nova-curation-hub', 'my-tickets'].includes(activeKey) || pathname.includes('settings') || pathname.includes('help') || pathname.includes('nova-curation-hub') || pathname.includes('my-tickets')) return 'profile';
    if (['ai-gallery', 'ai-marketplace'].includes(activeKey) || pathname.includes('feature-gallery') || pathname.includes('mini-apps')) return 'gallery';
    if (['ai-learning-hub', 'ai-coaching-team', 'ai-briefing'].includes(activeKey)) return 'coaching';
    if (['my-analytics', 'leaderboard', 'progress', 'certificate-gallery'].includes(activeKey) || pathname.includes('my-analytics') || pathname.includes('leaderboard') || pathname.includes('progress') || pathname.includes('certificate-gallery') || pathname.includes('certificate-operations')) return 'analytics';
    if (['payment-history', 'subscription'].includes(activeKey) || pathname.includes('payment-history') || pathname.includes('subscription')) return 'finance';
    if (['content-library', 'games-station', 'flappy-bird', 'watch-videos', 'audio-studio', 'my-podcasts', 'sports', 'notifications', 'integrations', 'book-meeting', 'calendar'].includes(activeKey) || pathname.includes('content-library') || pathname.includes('features/fps-game') || pathname.includes('features/flappy-bird') || pathname.includes('watch-videos') || pathname.includes('features/audio-studio') || pathname.includes('features/my-podcasts') || pathname.includes('features/sports') || pathname.includes('notifications') || pathname.includes('integrations') || pathname.includes('book-meeting') || pathname.includes('calendar')) return 'productivity';
    if (['id-checker', 'jobs-portal'].includes(activeKey) || pathname.includes('id-checker') || pathname.includes('id-verification') || pathname.includes('employer')) return 'security';
    return 'default';
  };
  const bgVariant = getBgVariant();
  const shouldRenderMobileBackground = false;
  const shouldRenderDesktopBackground = Platform.OS === 'web' && decorativeBackgroundReady && (!darkMode || bgVariant === 'home');

  const normalizedPathname = String(pathname || '/').split('?')[0].split('#')[0];
  const enableHeavyBackgroundPollers = [
    '/notifications',
    '/settings',
    '/executive-dashboard',
    '/admin',
  ].some((prefix) => normalizedPathname === prefix || normalizedPathname.startsWith(`${prefix}/`));
  const shouldShowRenewalBanner = showNonCriticalBanners && enableHeavyBackgroundPollers;
  const shouldShowOnboarding = deferNonCriticalReady && !whatsNewVisible && enableHeavyBackgroundPollers;

  /* ── Keyboard Shortcuts (Cmd/Ctrl + 1-9) ── */
  const SHORTCUT_MAP: Record<string, { key: string; href: string }> = useMemo(() => ({
      '1': { key: 'home', href: '/dashboard' },
    '2': { key: 'ai-gallery', href: '/feature-gallery' },
    '3': { key: 'ai-learning-hub', href: '/ai-learning-hub' },
    '4': { key: 'book-meeting', href: '/book-meeting' },
    '5': { key: 'my-analytics', href: '/my-analytics' },
    '6': { key: 'notifications', href: '/notifications' },
    '7': { key: 'settings', href: '/settings?section=novaAssistant' },
    '8': { key: 'help', href: '/help' },
      '9': { key: 'profile', href: '/profile' },
  }), []);

  // Reverse map: nav key → shortcut number
  const keyToShortcut = useMemo(() => {
    const map: Record<string, string> = {};
    for (const [num, v] of Object.entries(SHORTCUT_MAP)) map[v.key] = num;
    return map;
  }, [SHORTCUT_MAP]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handler = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const target = e.target as HTMLElement;
      if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable) return;
      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      const mapping = SHORTCUT_MAP[e.key];
      if (mapping) {
        e.preventDefault();
        router.push(mapping.href);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [SHORTCUT_MAP, router, toggleSidebar]);

  const handleLogout = () => {
    setShowSignOutConfirm(true);
  };

  const confirmLogout = async () => {
    setSigningOut(true);
    try {
      await logout();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/AppShell.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setSigningOut(false);
    setShowSignOutConfirm(false);
    router.replace('/auth/login?logout=1');
  };

  /* ── Mobile Drawer State ── */
  const drawerAnim = useRef(new Animated.Value(0)).current;
  const drawerScrollRef = useRef<any>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const openDrawer = () => {
    setDrawerOpen(true);
    requestAnimationFrame(() => {
      drawerScrollRef.current?.scrollTo?.({ y: 0, animated: false });
    });
    Animated.timing(drawerAnim, { toValue: 1, duration: 200, useNativeDriver: Platform.OS !== 'web' }).start();
  };
  const closeDrawer = () => {
    Animated.timing(drawerAnim, { toValue: 0, duration: 160, useNativeDriver: Platform.OS !== 'web' }).start(() => setDrawerOpen(false));
  };
  const translateX = drawerAnim.interpolate({ inputRange: [0, 1], outputRange: [-(mobileDrawerWidth + 16), 0] });
  const overlayOpacity = drawerAnim.interpolate({ inputRange: [0, 1], outputRange: [0, 0.55] });

  /* ── Nav Item Renderer ── */
  const tNav = (key: string, fallback: string) => {
    const tkey = NAV_TKEY[key];
    return tkey ? t(tkey) : fallback;
  };

  const renderNavItem = (item: any, isMobile = false) => {
    const collapsed = !isMobile && sidebarCollapsed;

    if (item.section) {
      if (collapsed) {
        return <View key={item.key} style={{ height: 24, justifyContent: 'center', alignItems: 'center' }}>
          <View style={{ width: 18, height: 1, backgroundColor: sidebarPalette.divider, borderRadius: 1 }} />
        </View>;
      }
      return (
        <View key={item.key} style={{ marginTop: isMobile ? 20 : 28, marginBottom: isMobile ? 6 : 8, paddingHorizontal: isMobile ? 16 : 18 }} data-testid={`section-${item.key}`} testID={`section-${item.key}`}>
          <Text style={{
            fontSize: 10.5, fontWeight: '800', letterSpacing: 1.6,
            textTransform: 'uppercase',
            color: sidebarPalette.sectionText,
            fontFamily: BODY_FONT_FAMILY,
          }}>{tNav(item.key, item.label)}</Text>
        </View>
      );
    }

    const active = item.key === activeKey;
    const isDanger = item.danger;

    const iconColor = isDanger ? colors.error : active ? sidebarPalette.itemIconActive : sidebarPalette.itemIconIdle;
    const labelColor = isDanger ? colors.error : active ? sidebarPalette.itemTextActive : sidebarPalette.itemTextIdle;
    const labelWeight: any = active ? '700' : '500';

    return (
      <TouchableOpacity key={item.key} activeOpacity={0.6}
        data-testid={`${isMobile ? 'mobile' : 'sidebar'}-nav-${item.key}`} testID={`${isMobile ? 'mobile' : 'sidebar'}-nav-${item.key}`}
        accessibilityRole="link"
        accessibilityLabel={tNav(item.key, item.label)}
        accessibilityState={{ selected: active }}
        onPress={() => {
          if (isMobile) closeDrawer();
          if (isDanger) { handleLogout(); return; }
          router.push(item.href);
        }}
        {...(collapsed && Platform.OS === 'web' ? { title: tNav(item.key, item.label) } : {})}
        style={{
          flexDirection: 'row', alignItems: 'center',
          position: 'relative' as const,
          gap: collapsed ? 0 : 11,
          paddingVertical: isMobile ? 10 : 10,
          paddingHorizontal: collapsed ? 0 : 12,
          paddingLeft: collapsed ? 0 : 16,
          marginHorizontal: collapsed ? 6 : 6,
          marginVertical: isMobile ? 1 : 1,
          borderRadius: 14,
          borderWidth: active && !isDanger ? 1 : 0,
          borderColor: active && !isDanger ? sidebarPalette.itemBorderActive : 'transparent',
          backgroundColor: active && !isDanger ? sidebarPalette.itemBgActive : 'transparent',
          ...(collapsed ? { justifyContent: 'center' as const, height: 42, borderRadius: 12 } : {}),
          ...(Platform.OS === 'web' ? {
            transition: 'all 0.18s cubic-bezier(0.4,0,0.2,1)',
          } as any : {}),
        }}>
        {/* Enterprise active indicator bar */}
        {active && !isDanger && !collapsed && (
          <View style={{
            position: 'absolute', left: 0, top: isMobile ? 8 : 7, bottom: isMobile ? 8 : 7,
            width: 3, borderRadius: 2, backgroundColor: colors.primary,
          }} />
        )}
        {active && !isDanger && collapsed && (
          <View style={{
            position: 'absolute', left: 4, top: 10, bottom: 10,
            width: 2.5, borderRadius: 2, backgroundColor: colors.primary,
          }} />
        )}
        <Ionicons name={item.icon as any} size={collapsed ? 19 : 17} color={iconColor} />
        {!collapsed && (
          <Text numberOfLines={1} style={{
            flex: 1, fontSize: 13.5, fontWeight: labelWeight,
            color: labelColor, letterSpacing: -0.15, fontFamily: BODY_FONT_FAMILY,
          }}>
            {tNav(item.key, item.label)}
          </Text>
        )}
        {!collapsed && item.key === 'notifications' ? <NotificationNavBadge testId={`${isMobile ? 'mobile' : 'sidebar'}-nav-notifications-badge`} /> : null}
        {collapsed && item.key === 'notifications' ? <NotificationNavBadge testId={`${isMobile ? 'mobile' : 'sidebar'}-nav-notifications-badge`} /> : null}
        {/* Keyboard shortcut hint (desktop only, expanded mode) */}
        {!collapsed && !isMobile && Platform.OS === 'web' && keyToShortcut[item.key] && (
          <View style={{
            paddingHorizontal: 5, paddingVertical: 2, borderRadius: 5,
            backgroundColor: sidebarPalette.chipBg,
            borderWidth: 0.5, borderColor: sidebarPalette.chipBorder,
          }} data-testid={`shortcut-hint-${item.key}`} testID={`shortcut-hint-${item.key}`}>
            <Text style={{
              fontSize: 9.5, fontWeight: '600',
              color: sidebarPalette.chipText,
              fontFamily: MONO_FONT_FAMILY,
            }}>
              {navigator?.platform?.includes('Mac') ? '\u2318' : 'Ctrl+'}{keyToShortcut[item.key]}
            </Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  /* ══════════════════════════════════════
     MOBILE LAYOUT  (< 1024px)
     ══════════════════════════════════════ */
  if (!isWide) {
    return (
      <NotificationProvider scope={resolvedNotificationScope}>
        <View style={{ flex: 1, backgroundColor: sidebarPalette.shellBg, position: 'relative' }} data-testid="app-shell-mobile" testID="app-shell-mobile">
          {/* Skip Navigation — Accessibility (hidden until focused) */}
          {Platform.OS === 'web' && (
            <a href="#main-content" data-testid="skip-nav-link" style={{
              position: 'absolute' as any, top: -9999, left: -9999, zIndex: 10000,
              backgroundColor: colors.primary, color: colors.primaryText, padding: '12px 24px',
              borderRadius: 8, fontWeight: 700, fontSize: 14, textDecoration: 'none',
            } as any} onFocus={(e: any) => { e.target.style.top = '8px'; e.target.style.left = '8px'; }}
              onBlur={(e: any) => { e.target.style.top = '-9999px'; e.target.style.left = '-9999px'; }}>
              {t('nav.skipToMain')}
            </a>
          )}
          {/* Background is deferred on web to protect first-paint performance. */}
          {shouldRenderMobileBackground && Platform.OS === 'web' && !darkMode && (
            <div style={{
              position: 'absolute' as const, inset: 0, zIndex: 0,
            }}>
              <PageFloatingBackground variant={bgVariant} />
            </div>
          )}
          {/* ── Top Bar — Enterprise V2 ── */}
          <View data-testid="mobile-top-bar" testID="mobile-top-bar" style={{
            paddingHorizontal: isTablet ? 20 : isUltraCompactMobile ? 12 : 16,
            paddingTop: isTablet ? 12 : 10,
            paddingBottom: isTablet ? 12 : 10,
            backgroundColor: colors.surfaceElevated,
            borderBottomWidth: 1,
            borderBottomColor: sidebarPalette.shellBorder,
          }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: isUltraCompactMobile ? 6 : 10 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: isUltraCompactMobile ? 8 : 10, flex: 1, minWidth: 0 }} data-testid="mobile-top-brand-wrap" testID="mobile-top-brand-wrap">
                <Image accessibilityLabel="logo image"
                  source={require('../../assets/images/logo.png')}
                  style={{ width: isTablet ? 32 : isUltraCompactMobile ? 24 : 28, height: isTablet ? 32 : isUltraCompactMobile ? 24 : 28, borderRadius: 7 }}
                  resizeMode="contain"
                  data-testid="mobile-top-brand-logo" testID="mobile-top-brand-logo"
                />
                <View style={{ flex: 1, minWidth: 0 }} data-notranslate>
                  <Text
                    numberOfLines={1}
                    adjustsFontSizeToFit
                    minimumFontScale={0.9}
                    style={{ fontSize: mobileBrandFontSize, fontWeight: '800', color: sidebarPalette.itemTextActive, letterSpacing: -0.3, fontFamily: DISPLAY_FONT_FAMILY }}
                    data-testid="mobile-top-brand-name" testID="mobile-top-brand-name"
                  >
                    Real<Text style={{ color: colors.primary }}>AI</Text>Coach
                  </Text>
                  <Text style={{ fontSize: 9.5, fontWeight: '700', color: colors.textMuted, marginTop: 1, letterSpacing: 1, textTransform: 'uppercase' as any, fontFamily: BODY_FONT_FAMILY }} data-testid="mobile-top-brand-subtitle" testID="mobile-top-brand-subtitle">
                    {t('app.enterpriseSuite')}
                  </Text>
                </View>
              </View>

              <View data-testid="mobile-header-action-group" testID="mobile-header-action-group" style={{ flexDirection: 'row', alignItems: 'center', gap: isUltraCompactMobile ? 4 : HEADER_ACTION_SNAPSHOT.mobileGap }}>
                {showMobileTopWhatsNew && <WhatsNewBadge compact onPress={() => notificationEvents.openWhatsNew()} onAutoOpen={handleWhatsNewAutoOpen} />}
                {isAuthenticated && deferNonCriticalReady && <NotificationBell />}
                <TouchableOpacity onPress={openDrawer} data-testid="mobile-nav-toggle" testID="mobile-nav-toggle" accessibilityRole="button" accessibilityLabel="Open navigation menu"
                  style={{ width: isUltraCompactMobile ? 34 : 38, height: isUltraCompactMobile ? 34 : 38, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: sidebarPalette.headerControlBg, borderWidth: 1, borderColor: sidebarPalette.divider }}>
                  <Ionicons name="menu" size={isUltraCompactMobile ? 18 : 20} color={sidebarPalette.headerControlIcon} />
                </TouchableOpacity>
              </View>
            </View>
          </View>

          {shouldShowRenewalBanner && <RenewalBanner />}
          {showNonCriticalBanners && <StartupRecoveryBanner />}
          <SessionTimeout />
          <View nativeID="main-content" style={{ flex: 1 }}>
            {children}
          </View>

          {/* ── Drawer Backdrop ── */}
          {drawerOpen && (
            <Pressable style={StyleSheet.absoluteFill} onPress={closeDrawer} data-testid="mobile-nav-overlay" testID="mobile-nav-overlay" accessibilityRole="button" >
              <Animated.View style={{
                flex: 1, opacity: overlayOpacity,
                ...(Platform.OS === 'web' ? {
                  backgroundColor: darkMode ? 'rgba(2,6,23,0.7)' : 'rgba(15,23,42,0.5)',
                  backdropFilter: 'blur(4px)', WebkitBackdropFilter: 'blur(4px)',
                } as any : { backgroundColor: colors.overlay }),
              }} />
            </Pressable>
          )}

          {/* ── Drawer Panel — Enterprise V2 ── */}
          <Animated.View data-testid="mobile-nav-drawer" testID="mobile-nav-drawer" style={{
            position: 'absolute', top: 0, bottom: 0, left: 0, width: mobileDrawerWidth,
            backgroundColor: sidebarPalette.shellBg,
            borderRightWidth: 1, borderRightColor: sidebarPalette.shellBorder,
            zIndex: 40, transform: [{ translateX }],
            ...(Platform.OS === 'web' ? {
              boxShadow: darkMode
                ? '6px 0 32px rgba(0,0,0,0.4), 2px 0 8px rgba(0,0,0,0.2)'
                : '6px 0 32px rgba(15,23,42,0.08), 2px 0 8px rgba(15,23,42,0.04)',
              display: 'flex', flexDirection: 'column',
            } as any : {}),
          }}>
            {/* Drawer Header — Brand + Close */}
            <View style={{
              flexDirection: 'row', alignItems: 'center', gap: 10,
              paddingHorizontal: 16, paddingTop: 20, paddingBottom: 16,
              borderBottomWidth: 1,
              borderBottomColor: sidebarPalette.divider,
            }}>
              <Image source={require('../../assets/images/logo.png')} style={{ width: 30, height: 30, borderRadius: 7 }} resizeMode="contain" accessibilityLabel="RealAICoach" />
              <View style={{ flex: 1 }} data-notranslate>
                <Text style={{ fontSize: 15, fontWeight: '800', color: sidebarPalette.itemTextActive, letterSpacing: -0.4 }}>
                  Real<Text style={{ color: colors.primary }}>AI</Text>Coach
                </Text>
                <Text style={{ fontSize: 9.5, fontWeight: '600', color: sidebarPalette.sectionText, letterSpacing: 0.8, textTransform: 'uppercase' as any, marginTop: 1 }}>{t('app.enterpriseSuite')}</Text>
              </View>
              <TouchableOpacity onPress={closeDrawer} data-testid="mobile-nav-close-btn" testID="mobile-nav-close-btn" style={{
                width: 30, height: 30, borderRadius: 8,
                alignItems: 'center', justifyContent: 'center',
                backgroundColor: sidebarPalette.headerControlBg,
                borderWidth: 1, borderColor: sidebarPalette.divider,
              }} accessibilityLabel="close button">
                <Ionicons name="close" size={15} color={sidebarPalette.headerControlIcon} />
              </TouchableOpacity>
            </View>

            {showDrawerWhatsNewShortcut ? (
              <View
                style={{
                  paddingHorizontal: 16,
                  paddingTop: 10,
                  paddingBottom: 2,
                  borderBottomWidth: 1,
                  borderBottomColor: sidebarPalette.divider,
                }}
                data-testid="mobile-drawer-whats-new-wrapper"
                testID="mobile-drawer-whats-new-wrapper"
              >
                <View style={{ alignSelf: 'flex-start' }}>
                  <WhatsNewBadge onPress={() => notificationEvents.openWhatsNew()} onAutoOpen={handleWhatsNewAutoOpen} />
                </View>
              </View>
            ) : null}

            {/* Drawer User Card */}
            <View style={{ paddingHorizontal: 12, paddingTop: 14, paddingBottom: 6 }}>
              <UserCard user={user} compact />
            </View>

            {/* Drawer Nav Items */}
            <ScrollView ref={drawerScrollRef} style={{ flex: 1 }} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingTop: 2, paddingBottom: 20, paddingHorizontal: 4 }}>
              {navItems.map(item => renderNavItem(item, true))}
            </ScrollView>

            {/* Drawer Footer */}
            <View style={{
              borderTopWidth: 1,
              borderTopColor: sidebarPalette.divider,
              paddingTop: 14, paddingBottom: 20, paddingHorizontal: 12, gap: 10,
            }}>
              {deferNonCriticalReady && <UsageLimitIndicator compact />}
              {isAuthenticated && deferNonCriticalReady && <WebPushPrompt userId={user?.user_id} />}
              {deferNonCriticalReady && <PwaInstallPrompt />}
              <ThemeToggle />
              <LanguageSwitcher />
            </View>
          </Animated.View>

          {deferNonCriticalReady && <NotificationOverlay />}
          <EnterpriseSignOutConfirmModal
            visible={showSignOutConfirm}
            loading={signingOut}
            onCancel={() => setShowSignOutConfirm(false)}
            onConfirm={confirmLogout}
            darkMode={darkMode}
            testIdPrefix="appshell-signout"
          />
        </View>
      </NotificationProvider>
    );
  }

  /* ══════════════════════════════════════
     DESKTOP LAYOUT  (>= 1024px)
     ══════════════════════════════════════ */
  const safeReturnTo = pathname || '/dashboard';

  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={isAuthenticated} returnTo={safeReturnTo}>
      <NotificationProvider scope={resolvedNotificationScope}>
        <View style={{ flex: 1, flexDirection: 'row', minHeight: '100%' as any, backgroundColor: sidebarPalette.shellBg }} data-testid="app-shell" testID="app-shell">
        {/* Skip Navigation — Accessibility (hidden until focused) */}
        {Platform.OS === 'web' && (
          <a href="#main-content" data-testid="skip-nav-link-desktop" style={{
            position: 'absolute' as any, top: -9999, left: -9999, zIndex: 10000,
            backgroundColor: colors.primary, color: colors.primaryText, padding: '12px 24px',
            borderRadius: 8, fontWeight: 700, fontSize: 14, textDecoration: 'none',
          } as any} onFocus={(e: any) => { e.target.style.top = '8px'; e.target.style.left = '270px'; }}
            onBlur={(e: any) => { e.target.style.top = '-9999px'; e.target.style.left = '-9999px'; }}>
            {t('nav.skipToMain')}
          </a>
        )}

        {/* Sidebar hover micro-interactions (web only, token-driven) */}
        {Platform.OS === 'web' && (
          <style dangerouslySetInnerHTML={{ __html: `
            [data-testid^="sidebar-nav-"] { transition: box-shadow .16s ease, transform .16s ease; }
            [data-testid^="sidebar-nav-"]:not([aria-selected="true"]):hover { box-shadow: inset 0 0 0 999px var(--app-surface-hover); transform: translateX(2px); }
          ` }} />
        )}

        {/* ── Sidebar ── */}
        <View data-testid="app-shell-sidebar" testID="app-shell-sidebar" accessibilityRole="navigation" accessibilityLabel="Main navigation sidebar"
          style={{
            width: sidebarCollapsed ? SIDEBAR_COLLAPSED : SIDEBAR_EXPANDED,
            borderRightWidth: 1,
            borderRightColor: sidebarPalette.shellBorder,
            backgroundColor: sidebarPalette.shellBg,
            paddingTop: 18,
            ...(Platform.OS === 'web' ? {
              position: 'sticky' as any, top: 0, height: '100vh' as any, overflowY: 'hidden' as any,
              display: 'flex' as any, flexDirection: 'column' as any, zIndex: 2,
              transition: 'width 0.22s cubic-bezier(0.4,0,0.2,1)',
              boxShadow: darkMode ? '8px 0 28px rgba(2,6,23,0.22)' : '8px 0 28px rgba(15,23,42,0.05)',
            } as any : {}),
          }}>

          {/* Brand + Toggle */}
          <View style={{ paddingHorizontal: sidebarCollapsed ? 0 : 18, marginBottom: 14 }} data-testid="app-shell-brand-icon" testID="app-shell-brand-icon">
            {sidebarCollapsed ? (
              /* Collapsed: logo centered + toggle below */
              <View style={{ alignItems: 'center', gap: 10 }}>
                <Image source={require('../../assets/images/logo.png')} style={{ width: 30, height: 30, borderRadius: 8 }} resizeMode="contain" accessibilityLabel="AI Logo" />
                <TouchableOpacity
                  data-testid="sidebar-collapse-toggle" testID="sidebar-collapse-toggle"
                  accessibilityRole="button" accessibilityLabel="Expand sidebar"
                  onPress={toggleSidebar}
                  style={{
                    width: 34, height: 34, borderRadius: 9,
                    alignItems: 'center', justifyContent: 'center',
                    backgroundColor: sidebarPalette.headerControlBg,
                    borderWidth: 1, borderColor: sidebarPalette.divider,
                    ...(Platform.OS === 'web' ? { transition: 'all 0.18s ease', cursor: 'pointer' } as any : {}),
                  }}>
                  <Ionicons name="chevron-forward" size={14} color={sidebarPalette.headerControlIcon} />
                </TouchableOpacity>
              </View>
            ) : (
              /* Expanded: full brand row + toggle */
              <>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}>
                  <Image source={require('../../assets/images/logo.png')} style={{ width: 34, height: 34, borderRadius: 9 }} resizeMode="contain" accessibilityLabel="AI Logo" />
                  <View style={{ flex: 1 }}>
                    <Text numberOfLines={1} style={{ fontSize: 16, fontWeight: '800', color: sidebarPalette.itemTextActive, letterSpacing: -0.4, fontFamily: DISPLAY_FONT_FAMILY }} data-testid="app-shell-brand" testID="app-shell-brand">
                      Real<Text style={{ color: colors.primary }}>AI</Text>Coach
                    </Text>
                    <Text style={{ fontSize: 9.5, fontWeight: '700', color: sidebarPalette.sectionText, letterSpacing: 0.8, textTransform: 'uppercase' as any, marginTop: 1, fontFamily: BODY_FONT_FAMILY }}>{t('app.enterpriseSuite')}</Text>
                    <Text style={{ fontSize: 11, color: colors.textMuted, marginTop: 5, fontFamily: BODY_FONT_FAMILY }} numberOfLines={1} data-testid="app-shell-brand-supporting-copy" testID="app-shell-brand-supporting-copy">
                      {isAdmin ? t('app.taglineAdmin') : t('app.taglineUser')}
                    </Text>
                  </View>
                  <TouchableOpacity
                    data-testid="sidebar-collapse-toggle" testID="sidebar-collapse-toggle"
                    accessibilityRole="button" accessibilityLabel="Collapse sidebar"
                    onPress={toggleSidebar}
                    style={{
                      width: 30, height: 30, borderRadius: 8,
                      alignItems: 'center', justifyContent: 'center',
                      backgroundColor: sidebarPalette.headerControlBg,
                      borderWidth: 1, borderColor: sidebarPalette.divider,
                      ...(Platform.OS === 'web' ? { transition: 'all 0.18s ease', cursor: 'pointer' } as any : {}),
                    }}>
                    <Ionicons name="chevron-back" size={13} color={sidebarPalette.headerControlIcon} />
                  </TouchableOpacity>
                </View>
                {isAuthenticated && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: HEADER_ACTION_SNAPSHOT.desktopGap, marginTop: 12, paddingLeft: 44 }} data-testid="desktop-sidebar-top-actions" testID="desktop-sidebar-top-actions">
                    {deferNonCriticalReady && <WhatsNewBadge compact onPress={() => notificationEvents.openWhatsNew()} onAutoOpen={handleWhatsNewAutoOpen} />}
                    {deferNonCriticalReady && <NotificationBell />}
                  </View>
                )}
              </>
            )}
          </View>
          <View style={{ height: 1, backgroundColor: sidebarPalette.divider, marginHorizontal: sidebarCollapsed ? 10 : 16, marginBottom: 6 }} />

          {/* Nav */}
          <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: 8, paddingTop: 2 }}>
            {navItems.map(item => renderNavItem(item, false))}
          </ScrollView>

          {/* Footer */}
          <View style={{
            borderTopWidth: 1,
            borderTopColor: sidebarPalette.divider,
            paddingVertical: 14, paddingHorizontal: sidebarCollapsed ? 8 : 12, gap: sidebarCollapsed ? 8 : 10,
            alignItems: sidebarCollapsed ? 'center' : 'stretch',
          }}>
            {sidebarCollapsed ? (
              /* Collapsed footer: just avatar */
              <>
                {user && (
                  <TouchableOpacity
                    onPress={() => router.push('/profile')}
                    data-testid="sidebar-collapsed-user-avatar" testID="sidebar-collapsed-user-avatar"
                    accessibilityLabel={user.name || user.email || 'Profile'}
                    {...(Platform.OS === 'web' ? { title: user.name || user.email } : {})}
                    style={{
                      width: 34, height: 34, borderRadius: 17, overflow: 'hidden' as const,
                      backgroundColor: (globalThis as any).__alphaColor(colors.primary, '20'),
                      alignItems: 'center', justifyContent: 'center',
                      borderWidth: 1.5, borderColor: (globalThis as any).__alphaColor(colors.primary, '30'),
                    }}>
                    {user.profile_image ? (
                      Platform.OS === 'web' ? (
                        <img src={user.profile_image} style={{ width: 34, height: 34, borderRadius: 17, objectFit: 'cover' } as any} alt="" />
                      ) : (
                        <Image source={{ uri: user.profile_image }} style={{ width: 34, height: 34, borderRadius: 17 }} accessibilityLabel="profile" />
                      )
                    ) : (
                      <Text style={{ fontSize: 13, fontWeight: '700', color: colors.primary }}>
                        {(user.name || user.email || '?')[0].toUpperCase()}
                      </Text>
                    )}
                  </TouchableOpacity>
                )}
              </>
            ) : (
              /* Expanded footer: full details */
              <>
                <UserCard user={user} />
                {deferNonCriticalReady && <UsageLimitIndicator />}
                {isAuthenticated && deferNonCriticalReady && <WebPushPrompt userId={user?.user_id} />}
                {deferNonCriticalReady && <PwaInstallPrompt />}
                <ThemeToggle />
                <LanguageSwitcher />
              </>
            )}
          </View>
        </View>

        {/* ── Content ── */}
        <View nativeID="main-content" accessibilityRole="main" style={{ flex: 1, overflow: 'hidden' as any, position: 'relative' as any, backgroundColor: colors.background }}>
          {/* Background is deferred on desktop web to avoid slowing first render. */}
          {shouldRenderDesktopBackground && (
            <div style={{
              position: 'absolute' as const, inset: 0, zIndex: 0,
            }}>
              <PageFloatingBackground variant={bgVariant} />
            </div>
          )}
          <GlobalNavBar dimmed={whatsNewVisible} />
          {shouldShowRenewalBanner && <RenewalBanner />}
          <SessionTimeout />
          {showNonCriticalBanners && <WelcomeBackBanner />}
          {showNonCriticalBanners && <StartupRecoveryBanner />}
          {children}
          {deferNonCriticalReady && <TeamNotificationToasts />}
        </View>

        {deferNonCriticalReady && <NotificationOverlay />}
        {shouldShowOnboarding && <SmartOnboarding />}
        <EnterpriseSignOutConfirmModal
          visible={showSignOutConfirm}
          loading={signingOut}
          onCancel={() => setShowSignOutConfirm(false)}
          onConfirm={confirmLogout}
          darkMode={darkMode}
          testIdPrefix="appshell-signout"
        />
        </View>
      </NotificationProvider>
    </ProtectedRouteGate>
  );
}
