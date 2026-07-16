import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Stack, usePathname, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { Text, TextInput, View, Platform, ActivityIndicator, TouchableOpacity } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SplashScreen from 'expo-splash-screen';
import {
  useFonts,
  Manrope_400Regular,
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import { AuthProvider, useAuth } from '../src/context/AuthContext';
import { ThemeProvider, useTheme } from '../src/context/ThemeContext';
import { SubscriptionProvider } from '../src/context/SubscriptionContext';
import { AccessControlProvider } from '../src/context/AccessControlContext';
import FeatureQuotaPill from '../src/components/FeatureQuotaPill';
import SuggestedSpecialistsStrip from '../src/components/SuggestedSpecialistsStrip';
import { AccessibilityProvider } from '../src/context/AccessibilityContext';
import { LanguageProvider } from '../src/i18n/LanguageContext';
import { GlobalTranslationProvider } from '../src/providers/GlobalTranslationProvider';
import { ConfigProvider } from '../src/context/ConfigContext';
import { FeaturesProvider } from '../src/context/FeaturesContext';
import { RealtimeProvider } from '../src/context/RealtimeContext';
import { LocationProvider } from '../src/context/LocationContext';
import { BackgroundBrightnessProvider } from '../src/context/BackgroundBrightnessContext';
import { GLSProvider } from '../src/context/GLSContext';
import { usePushNotifications } from '../src/hooks/usePushNotifications';
import RealtimeToast from '../src/components/RealtimeToast';
import { ErrorBoundary } from '../src/components/ErrorBoundary';
import RouteAccessGuard from '../src/components/RouteAccessGuard';
import { ThemeEnforcer } from '../src/components/ThemeEnforcer';
import { ThemeComplianceRuntimeGate } from '../src/components/ThemeComplianceRuntimeGate';
import { UIEMProvider } from '../src/uiem/UIEMContext';
import { UIEMWatchdog } from '../src/uiem/UIEMWatchdog';
import { clearCache as clearApiCache } from '../src/services/api';
import { subscribeGlobalLoading } from '../src/services/loadingOrchestrator';
import { reportPreviewHealth } from '../src/services/previewHealthMonitor';
import { EnterpriseBootSplash, EnterpriseTransitionOverlay } from '../src/components/branding/EnterpriseMotionOverlay';
import { PERFORMANCE_STANDARDS } from '../src/config/performanceStandards';
import { resolveMiniAppRedirect } from '../src/config/miniAppRedirects';
import { ensureGlobalAlphaColor, withAlpha } from '../src/utils/colorAlpha';

// Direct imports for components that fail to lazy-load in this environment
import SafeUpdateBanner from '../src/components/SafeUpdateBanner';
import { OfflineBanner } from '../src/components/OfflineBanner';
import { RealtimeReconnectBanner } from '../src/components/RealtimeReconnectBanner';
import { GpsDegradedGlobalBanner } from '../src/components/GpsDegradedGlobalBanner';
import StartupRecoveryBanner from '../src/components/StartupRecoveryBanner';
import PWAInstallBanner from '../src/components/PWAInstallBanner';
import SubscriptionUpgradeModal from '../src/components/SubscriptionUpgradeModal';
import { GlobalMaintenanceOverlay } from '../src/components/GlobalMaintenanceOverlay';
import { GlobalPlatformRouteGuard } from '../src/components/GlobalPlatformRouteGuard';
import { PreviewHostRecoveryBanner } from '../src/components/PreviewHostRecoveryBanner';
import { PreviewShellMismatchBanner } from '../src/components/PreviewShellMismatchBanner';

// Direct imports (no lazy loading to avoid Metro lazy=true mode which causes ERR_ABORTED)
import { ColorBlindFilters } from '../src/components/accessibility/ColorBlindFilters';
import { SkipToContent as SkipToContentComp, LiveRegion as LiveRegionComp, announceToScreenReader } from '../src/components/accessibility/SkipToContent';
import { useWebVitals } from '../src/hooks/useWebVitals';
import { useUiRouteGuards } from '../src/hooks/useUiRouteGuards';
import { useAppStore } from '../src/store/appStore';

import { WhatsNewModal } from '../src/components/changelog/WhatsNewModal';
import TosAcceptanceModal from '../src/components/TosAcceptanceModal';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';

/**
 * WhatsNew portal rendered at the root level.
 * Lives OUTSIDE the Expo router Stack, so it never gets unmounted by route transitions.
 * Uses plain useState + useEffect (safe because _layout.tsx never unmounts).
 */
function WhatsNewRootPortal() {
  const [visible, setVisible] = useState(false);
  const pathname = usePathname();
  useEffect(() => {
    // Web-only: relies on window/document globals + a custom DOM event fired
    // by notificationEvents. On native (iOS/Android) these globals are
    // undefined and accessing them crashes the whole app (black screen in
    // the Expo Go / platform mobile preview). Short-circuit safely.
    if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') return;
    const handler = () => {
      const ne = (window as any).__notificationEvents;
      setVisible(ne ? ne.whatsNewVisible : false);
    };
    document.addEventListener('ne:whats-new', handler);
    const ne = (window as any).__notificationEvents;
    if (ne) setVisible(ne.whatsNewVisible);
    return () => document.removeEventListener('ne:whats-new', handler);
  }, []);
  if (pathname?.includes('job-platform') || pathname?.includes('mini-apps/job-platform') || pathname?.includes('employer-apply')) return null;
  if (!visible) return null;
  return <WhatsNewModal visible={visible} onClose={() => { const ne = (window as any).__notificationEvents; if (ne) ne.closeWhatsNew(); }} />;
}

SplashScreen.preventAutoHideAsync();

async function clearLegacyCachesOnce() {
  const existing = await AsyncStorage.getItem('cache_schema_version');
  if (existing === PERFORMANCE_STANDARDS.cacheSchemaVersion) return;

  clearApiCache();

  const asyncLegacyKeys = [
    'legacy_theme_mode',
    'legacy_dark_mode',
    'legacy_language_cache',
    'legacy_subscription_cache',
    'legacy_access_control_cache',
    'legacy_profile_cache',
    'legacy_route_cache',
    'legacy_notifications_cache',
    'stale_pref_cache',
    'home-dashboard-stats-snapshot',
    'ai-learning-hub-cache-schema',
  ];

  const browserStoragePrefixes = [
    'legacy_',
    'cache_',
    'stale_',
    'tx_cache_',
    'live_query_snapshot_v1:',
    'ai-learning-hub-legacy-',
    'ai-learning-hub-cache-',
    'ai-learning-hub-roadmap-progress-',
  ];

  const browserStorageExactKeys = new Set([
    ...asyncLegacyKeys,
    'home-dashboard-stats-snapshot',
    'ai-learning-hub-cache-schema',
  ]);

  await AsyncStorage.multiRemove(asyncLegacyKeys).catch(() => {});

  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const protectedKeys = new Set([
      'session_token',
      'refresh_token',
      'cache_schema_version',
      PERFORMANCE_STANDARDS.bootAnimationVersion,
    ]);

    const clearBrowserStorage = (storage?: Storage | null) => {
      if (!storage) return;
      Object.keys(storage).forEach((key) => {
        if (protectedKeys.has(key)) return;
        if (browserStorageExactKeys.has(key) || browserStoragePrefixes.some((prefix) => key.startsWith(prefix))) {
          storage.removeItem(key);
        }
      });
    };

    clearBrowserStorage(window.localStorage);
    clearBrowserStorage(window.sessionStorage);

    if ('caches' in window) {
      const cacheKeys = await window.caches.keys();
      await Promise.all(cacheKeys.map((cacheKey) => window.caches.delete(cacheKey))).catch((error) => {
        handleAppRecoverableError({
          scope: '_layout.clear-preview-caches',
          error,
          message: 'Could not clear stale preview caches.',
          onRetry: () => { window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      });
    }

    window.localStorage.setItem('cache_schema_version', PERFORMANCE_STANDARDS.cacheSchemaVersion);
  }

  await AsyncStorage.setItem('cache_schema_version', PERFORMANCE_STANDARDS.cacheSchemaVersion).catch((error) => {
    handleAppRecoverableError({
      scope: '_layout.cache-schema-version-write',
      error,
      message: 'Could not persist cache schema version.',
      onRetry: () => { window.location.reload(); },
    
        notifyMode: 'dialog',
        userInitiated: true,
      });
  });
}

function PushNotificationRegistrar() {
  const { user } = useAuth();
  usePushNotifications(user?.user_id);

  // Register service worker on web for push notifications
  React.useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!('serviceWorker' in navigator)) return;
    const host = String(window.location.hostname || '').toLowerCase();
    const isEmbedded = (() => {
      try {
        return window.self !== window.top;
      } catch {
        return true;
      }
    })();
    const isPreviewHost =
      host.includes('preview.emergentagent.com') ||
      host.includes('.preview.emergentcf.cloud') ||
      host.endsWith('.emergent.sh') ||
      host === 'app.emergent.sh';

    if (isPreviewHost || isEmbedded) {
      const guardKey = 'rac:sw-preview-cleanup-v1';
      if ((window as any).__racSwPreviewCleanupRunning) return;
      (window as any).__racSwPreviewCleanupRunning = true;

      (async () => {
        try {
          const registrations = await navigator.serviceWorker.getRegistrations();
          await Promise.all(registrations.map((registration) => registration.unregister().catch(() => {})));
          if ('caches' in window) {
            const cacheKeys = await caches.keys();
            await Promise.all(
              cacheKeys
                .filter((cacheKey) => cacheKey.startsWith('realaicoach-') || cacheKey.startsWith('workbox-'))
                .map((cacheKey) => caches.delete(cacheKey).catch(() => {}))
            );
          }

          const shouldReload = Boolean(navigator.serviceWorker.controller);
          const alreadyReloaded = sessionStorage.getItem(guardKey) === '1';
          if (shouldReload && !alreadyReloaded) {
            sessionStorage.setItem(guardKey, '1');
            window.location.reload();
          }
        } catch (error) {
          handleAppRecoverableError({
            scope: '_layout.tsx#catch1',
            error,
            message: 'Something went wrong. Please retry.',
            notifyMode: 'silent',
          });
        }
      })();

      console.log('[SW] Disabled and cleaned in preview/embed context:', { host, isEmbedded });
      return;
    }
    if ((window as any).__racSwBootstrapped) return;
    (window as any).__racSwBootstrapped = true;

    navigator.serviceWorker.register('/sw.js').then((reg) => {
      console.log('[SW] Service worker registered, scope:', reg.scope);

      // Self-healing: when a new SW has taken over (happens after we bump
      // cache versions) force a one-time reload so the page picks up the
      // fresh chunk manifest. Without this, in-flight clients continue
      // using the stale bundle and crash with "Loading chunk X failed"
      // → React error boundary → the "Something Went Wrong" outage.
      let reloading = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (reloading) return;
        reloading = true;
        console.log('[SW] New controller took over — reloading to load fresh chunks.');
        window.location.reload();
      });

      // When a new SW version is discovered, tell it to activate immediately.
      reg.addEventListener('updatefound', () => {
        const nw = reg.installing;
        if (!nw) return;
        nw.addEventListener('statechange', () => {
          if (nw.state === 'installed' && navigator.serviceWorker.controller) {
            nw.postMessage({ type: 'SKIP_WAITING' });
          }
        });
      });
    }).catch((err) => {
      console.warn('[SW] Registration failed:', err);
    });

    // Absolute last-resort chunk-load-error recovery: if any async chunk
    // 404s (because the user has a stale SW pointing at a bundle name that
    // no longer exists), unregister all SWs, wipe caches, and hard-reload
    // — once per session only, so we never loop.
    const sessionKey = 'rac:chunk-error-recovery-attempted';
    const handler = (evt: ErrorEvent | PromiseRejectionEvent) => {
      const anyEvt = evt as any;
      const msg = String(anyEvt?.message || anyEvt?.reason || '');
      const looksLikeChunkError = (
        /Loading chunk\s+\S+\s+failed/i.test(msg) ||
        /ChunkLoadError/i.test(msg) ||
        /Loading CSS chunk/i.test(msg) ||
        /Failed to fetch dynamically imported module/i.test(msg) ||
        /Importing a module script failed/i.test(msg)
      );
      if (!looksLikeChunkError) return;
      try {
        if (sessionStorage.getItem(sessionKey) === '1') return;
        sessionStorage.setItem(sessionKey, '1');
      } catch (error) {
        handleAppRecoverableError({
          scope: '_layout.chunk-recovery-session-guard',
          error,
          message: 'Could not persist chunk-recovery guard.',
          onRetry: () => { window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      }
      console.warn('[SW] Chunk-load error detected — self-healing SW + caches', msg);
      (async () => {
        try {
          const regs = await navigator.serviceWorker.getRegistrations();
          await Promise.all(regs.map((r) => r.unregister().catch(() => {})));
          if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map((k) => caches.delete(k).catch(() => {})));
          }
        } catch (error) {
          handleAppRecoverableError({
            scope: '_layout.chunk-recovery-cleanup',
            error,
            message: 'Chunk recovery cleanup failed.',
            onRetry: () => { window.location.reload(); },
          
        notifyMode: 'dialog',
        userInitiated: true,
      });
        } finally {
          window.location.reload();
        }
      })();
    };
    window.addEventListener('error', handler as any);
    window.addEventListener('unhandledrejection', handler as any);
  }, []);

  return null;
}

function AccessibilityWrapper({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return (
    <AccessibilityProvider userId={user?.user_id}>
      <ColorBlindFilters />
      {children}
    </AccessibilityProvider>
  );
}

function ThemeAwareStatusBar() {
  const { darkMode } = useTheme();
  return <StatusBar style={darkMode ? 'light' : 'dark'} />;
}

function EnterpriseMotionCoordinator() {
  const pathname = usePathname();
  const [bootDecisionReady, setBootDecisionReady] = useState(false);
  const [showBootSplash, setShowBootSplash] = useState(false);
  const [showTransition, setShowTransition] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const isTransitionVisible = useRef(false);
  const previousPath = useRef(pathname);
  const routeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadingShowTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadingHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bootReadyFallbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const bootSplashForceHideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastVisibleAt = useRef(0);

  const shouldSkipNonCriticalMotion = useCallback(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') {
      return false;
    }

    const isAuthLikeRoute = pathname === '/' || pathname === '/welcome' || pathname?.startsWith('/auth');
    const isAdminWorkRoute = pathname?.includes('admin-console') || pathname?.includes('executive-dashboard');
    try {
      return isAuthLikeRoute || isAdminWorkRoute || window.self !== window.top;
    } catch {
      return true;
    }
  }, [pathname]);

  const hideTransition = (minVisibleMs = PERFORMANCE_STANDARDS.loadingOverlayMinVisibleMs) => {
    if (loadingHideTimer.current) {
      clearTimeout(loadingHideTimer.current);
      loadingHideTimer.current = null;
    }

    const elapsed = Date.now() - lastVisibleAt.current;
    const delay = Math.max(0, minVisibleMs - elapsed);
    loadingHideTimer.current = setTimeout(() => {
      isTransitionVisible.current = false;
      setShowTransition(false);
    }, delay);
  };

  const showTransitionNow = () => {
    if (isTransitionVisible.current) return;
    lastVisibleAt.current = Date.now();
    isTransitionVisible.current = true;
    setShowTransition(true);
  };

  useEffect(() => {
    let cancelled = false;

    const reduceByNetwork =
      Platform.OS === 'web' &&
      typeof navigator !== 'undefined' &&
      (navigator as any).connection?.saveData;

    const reduceByPreference =
      Platform.OS === 'web' &&
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const reduce = Boolean(reduceByNetwork || reduceByPreference || shouldSkipNonCriticalMotion());
    setReduceMotion(reduce);

    if (bootReadyFallbackTimer.current) {
      clearTimeout(bootReadyFallbackTimer.current);
      bootReadyFallbackTimer.current = null;
    }

    bootReadyFallbackTimer.current = setTimeout(() => {
      if (cancelled) return;
      setShowBootSplash(false);
      setBootDecisionReady(true);
    }, 1800);

    (async () => {
      try {
        const seen = await AsyncStorage.getItem(PERFORMANCE_STANDARDS.bootAnimationVersion);
        if (cancelled) return;
        const shouldShowBoot = !seen && !reduce;
        setShowBootSplash(shouldShowBoot);
      } catch {
        if (!cancelled) {
          setShowBootSplash(false);
        }
      } finally {
        if (bootReadyFallbackTimer.current) {
          clearTimeout(bootReadyFallbackTimer.current);
          bootReadyFallbackTimer.current = null;
        }
        if (!cancelled) {
          setBootDecisionReady(true);
        }
      }
    })();

    return () => {
      cancelled = true;
      if (bootReadyFallbackTimer.current) {
        clearTimeout(bootReadyFallbackTimer.current);
        bootReadyFallbackTimer.current = null;
      }
    };
  }, [shouldSkipNonCriticalMotion]);

  useEffect(() => {
    if (reduceMotion) return;
    const unsubscribe = subscribeGlobalLoading((activeCount) => {
      if (loadingShowTimer.current) {
        clearTimeout(loadingShowTimer.current);
        loadingShowTimer.current = null;
      }

      if (activeCount > 0) {
        loadingShowTimer.current = setTimeout(
          () => showTransitionNow(),
          PERFORMANCE_STANDARDS.loadingOverlayDebounceMs,
        );
      } else {
        hideTransition();
      }
    });

    return () => {
      unsubscribe();
      if (loadingShowTimer.current) clearTimeout(loadingShowTimer.current);
      if (loadingHideTimer.current) clearTimeout(loadingHideTimer.current);
    };
  }, [reduceMotion]);

  useEffect(() => {
    if (reduceMotion) return;
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;

    if (routeTimer.current) clearTimeout(routeTimer.current);
    showTransitionNow();
    routeTimer.current = setTimeout(() => hideTransition(140), PERFORMANCE_STANDARDS.routeTransitionVisibleMs);

    return () => {
      if (routeTimer.current) clearTimeout(routeTimer.current);
    };
  }, [pathname, reduceMotion]);

  useEffect(() => {
    if (!showBootSplash) {
      if (bootSplashForceHideTimer.current) {
        clearTimeout(bootSplashForceHideTimer.current);
        bootSplashForceHideTimer.current = null;
      }
      return;
    }

    bootSplashForceHideTimer.current = setTimeout(() => {
      setShowBootSplash(false);
    }, PERFORMANCE_STANDARDS.bootAnimationDurationMs + 1400);

    return () => {
      if (bootSplashForceHideTimer.current) {
        clearTimeout(bootSplashForceHideTimer.current);
        bootSplashForceHideTimer.current = null;
      }
    };
  }, [showBootSplash]);

  const handleBootDone = useCallback(() => {
    setShowBootSplash(false);
    void AsyncStorage.setItem(PERFORMANCE_STANDARDS.bootAnimationVersion, '1');
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      window.localStorage.setItem(PERFORMANCE_STANDARDS.bootAnimationVersion, '1');
    }
  }, []);

  if (!bootDecisionReady) {
    return null;
  }

  return (
    <>
      <EnterpriseTransitionOverlay visible={!reduceMotion && showTransition} />
      <EnterpriseBootSplash
        visible={showBootSplash}
        onDone={handleBootDone}
        durationMs={PERFORMANCE_STANDARDS.bootAnimationDurationMs}
      />
    </>
  );
}

// PWAInstallBanner is lazy-loaded above

function RouteAnnouncer() {
  const pathname = usePathname();
  const prevPath = React.useRef(pathname);
  React.useEffect(() => {
    if (Platform.OS !== 'web' || pathname === prevPath.current) return;
    prevPath.current = pathname;
    const label = pathname === '/' || pathname === '/(tabs)' ? 'Dashboard'
      : pathname.replace(/^\/|[-/]/g, m => m === '/' ? ', ' : ' ').trim();
    announceToScreenReader(`Navigated to ${label}`);
  }, [pathname]);
  return null;
}

function MiniAppRouteRedirector() {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const target = resolveMiniAppRedirect(pathname, { isAuthenticated });
    if (!target || target === pathname) return;
    router.replace(target as any);
  }, [isAuthenticated, pathname, router]);

  return null;
}

function PreviewHealthReporter() {
  const pathname = usePathname();

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    const timer = window.setTimeout(() => {
      void reportPreviewHealth('layout_mounted', { pathname });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [pathname]);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;

    const onVisibility = () => {
      void reportPreviewHealth('visibility_change', {
        pathname,
        visibility: document.visibilityState,
      });
    };

    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [pathname]);

  return null;
}

function WebVitalsReporter() {
  useWebVitals();
  return null;
}

function UiRouteGuardReporter() {
  useUiRouteGuards();
  return null;
}

function GlobalWhiteScreenGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const { colors } = useTheme();
  const [visible, setVisible] = useState(false);
  const [reason, setReason] = useState('render_stall');
  const [detectedAt, setDetectedAt] = useState('');

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof document === 'undefined') return;

    let blankTicks = 0;
    setVisible(false);
    setReason('render_stall');
    setDetectedAt('');

    const hasMeaningfulContent = () => {
      const root = document.getElementById('root');
      if (!root) return false;
      if (document.getElementById('app-loading-fallback')) return true;

      const textLength = (root.innerText || '').replace(/\s+/g, '').length;
      const elementCount = root.querySelectorAll('*').length;
      const richMediaCount = root.querySelectorAll('img,svg,canvas,video,iframe').length;
      const hasKnownFallback = !!root.querySelector('[data-testid="root-loading-fallback"], [data-testid="error-boundary"]');

      if (hasKnownFallback) return true;
      return textLength > 40 || elementCount > 55 || richMediaCount > 0;
    };

    const markWhiteScreen = (nextReason: string, force = false) => {
      if (!force && hasMeaningfulContent()) return;
      setReason(nextReason);
      setDetectedAt(new Date().toISOString());
      setVisible(true);
      void reportPreviewHealth('white_screen_detected', {
        reason: nextReason,
        pathname,
      });
    };

    const interval = window.setInterval(() => {
      const root = document.getElementById('root');
      if (!root) return;
      const appReady = root.getAttribute('data-app-ready') === 'true';
      if (!appReady) {
        blankTicks = 0;
        return;
      }

      if (hasMeaningfulContent()) {
        blankTicks = 0;
        setVisible(false);
        return;
      }

      blankTicks += 1;
      if (blankTicks >= 3) {
        markWhiteScreen('dom_blank_after_ready');
      }
    }, 1500);

    const extractReasonText = (payload: any) => {
      if (!payload) return '';
      if (typeof payload === 'string') return payload;
      // Handle PromiseRejectionEvent
      if (payload?.reason) {
        const reason = payload.reason;
        if (typeof reason === 'string') return reason;
        if (reason?.message && typeof reason.message === 'string') return reason.message;
        // Handle Error objects
        if (reason instanceof Error) return reason.message || reason.toString();
        if (reason?.toString) return reason.toString();
      }
      if (payload?.message && typeof payload.message === 'string') return payload.message;
      // Handle ErrorEvent
      if (payload?.error?.message) return payload.error.message;
      if (payload?.error?.toString) return payload.error.toString();
      if (payload?.toString) return payload.toString();
      // Try to stringify the payload
      try {
        return JSON.stringify(payload);
      } catch {
        return '';
      }
    };

    const isIgnorableError = (payload: any) => {
      const text = extractReasonText(payload).toLowerCase();
      // Ignore only intentional abort-style interruptions.
      if (text.includes('err_aborted') || text.includes('aborterror') || text.includes('the user aborted a request')) return true;
      // Ignore expected auth probe misses only.
      if (text.includes('401') && text.includes('/api/auth/me')) return true;
      // Keep rate-limit noise out of white-screen guard.
      if (text.includes('429') || text.includes('rate limit') || text.includes('too many requests')) return true;
      return false;
    };

    const classifyCriticalErrorReason = (payload: any, fallback: string) => {
      const text = extractReasonText(payload).toLowerCase();
      if (text.includes('cors') || text.includes('cross-origin')) return `${fallback}_cors`;
      if (text.includes('loading chunk') || text.includes('chunkloaderror') || text.includes('route') && text.includes('not found')) return `${fallback}_route_chunk`;
      if (text.includes('request failed') || text.includes('fetch failed') || text.includes('networkerror') || text.includes('net::err')) return `${fallback}_network`;
      if (text.includes('websocket') || text.includes('ws://') || text.includes('wss://')) return `${fallback}_websocket`;
      return fallback;
    };

    const onError = (event: any) => {
      if (isIgnorableError(event)) return;
      const reasonCode = classifyCriticalErrorReason(event, 'runtime_error');
      window.setTimeout(() => {
        if (!hasMeaningfulContent()) {
          markWhiteScreen(reasonCode, false);
        }
      }, 500);
    };

    const onRejection = (event: any) => {
      if (isIgnorableError(event)) return;
      const reasonCode = classifyCriticalErrorReason(event, 'unhandled_rejection');
      window.setTimeout(() => {
        if (!hasMeaningfulContent()) {
          markWhiteScreen(reasonCode, false);
        }
      }, 500);
    };
    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onRejection);

    return () => {
      window.clearInterval(interval);
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onRejection);
    };
  }, [pathname]);

  if (Platform.OS !== 'web' || !visible) return null;

  return (
    <View
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
        zIndex: 999999,
        backgroundColor: 'var(--app-bg, #050A18)' as any, // @theme-ok css-var-fallback (runtime override sets --app-bg from theme)
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 22,
      }}
      data-testid="global-white-screen-guard"
      testID="global-white-screen-guard"
    >
      <View style={{ width: '100%', maxWidth: 420, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(20,184,166,0.28)', backgroundColor: 'rgba(15,23,42,0.94)', padding: 18 }} data-testid="global-white-screen-guard-card" testID="global-white-screen-guard-card">
        {/* @theme-ok — white-screen guard renders on an intentionally always-dark emergency backdrop so users recognise it as a system recovery overlay regardless of the active theme (same pattern as UIEMWatchdog + AttachmentLightbox). */}
        <Text style={{ color: '#E6EAF2' /* @theme-ok always-dark emergency */, fontSize: 18, fontWeight: '800' }} data-testid="global-white-screen-guard-title" testID="global-white-screen-guard-title">Recovery Guard Activated{/* @theme-ok */}</Text>
        <Text style={{ color: '#9AA4B2' /* @theme-ok always-dark emergency */ /* @theme-ok */, fontSize: 12, lineHeight: 19, marginTop: 8 }} data-testid="global-white-screen-guard-copy" testID="global-white-screen-guard-copy">
          We detected a blank-render state and activated fail-safe recovery so the platform never stays on a white screen.{/* @theme-ok */}
        </Text>

        <View style={{ marginTop: 10, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(31,41,55,0.9)', backgroundColor: 'rgba(11,18,32,0.72)', padding: 10 }} data-testid="global-white-screen-guard-meta" testID="global-white-screen-guard-meta">
          {/* @theme-ok — see above; always-dark emergency card */}
          <Text style={{ color: '#9AA4B2' /* @theme-ok always-dark emergency */, fontSize: 11 }} data-testid="global-white-screen-guard-route" testID="global-white-screen-guard-route">Route: {pathname || '/'}{/* @theme-ok */}</Text>
          <Text style={{ color: '#9AA4B2' /* @theme-ok always-dark emergency */, fontSize: 11, marginTop: 3 }} data-testid="global-white-screen-guard-reason" testID="global-white-screen-guard-reason">Reason: {reason}{/* @theme-ok */}</Text>
          <Text style={{ color: '#9AA4B2' /* @theme-ok always-dark emergency */, fontSize: 11, marginTop: 3 }} data-testid="global-white-screen-guard-time" testID="global-white-screen-guard-time">Detected: {detectedAt ? detectedAt.replace('T', ' ').slice(0, 19) : 'now'}{/* @theme-ok */}</Text>
        </View>

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
          <TouchableOpacity
            onPress={() => window.location.reload()}
            style={{ flex: 1, minWidth: 120, borderRadius: 10, backgroundColor: colors.accent, paddingVertical: 10, paddingHorizontal: 12, alignItems: 'center' }}
            data-testid="global-white-screen-guard-reload"
            testID="global-white-screen-guard-reload"
          >
            <Text style={{ color: '#04101F' /* @theme-ok deliberate-high-contrast: dark text on teal accent button — correct contrast */, fontSize: 12, fontWeight: '800' }}>Reload App</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.replace('/(tabs)' as any)}
            style={{ flex: 1, minWidth: 120, borderRadius: 10, borderWidth: 1, borderColor: 'rgba(20,184,166,0.38)', backgroundColor: 'rgba(20,184,166,0.12)', paddingVertical: 10, paddingHorizontal: 12, alignItems: 'center' }}
            data-testid="global-white-screen-guard-home"
            testID="global-white-screen-guard-home"
          >
            <Text style={{ color: '#5EEAD4' /* @theme-ok: teal text on translucent teal button (always-dark emergency guard) */, fontSize: 12, fontWeight: '700' }}>Go Home</Text>
          </TouchableOpacity>

          <TouchableOpacity
            onPress={() => router.replace('/auth/login' as any)}
            style={{ width: '100%', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(31,41,55,1)', backgroundColor: 'rgba(11,18,32,0.56)', paddingVertical: 10, alignItems: 'center' }}
            data-testid="global-white-screen-guard-login"
            testID="global-white-screen-guard-login"
          >
            <Text style={{ color: '#9AA4B2' /* @theme-ok: always-dark emergency guard */, fontSize: 12, fontWeight: '700' }}>Open Login Route</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

function GlobalLanguageSwitchOverlay() {
  const { languageCode, languageSwitching, colors } = useTheme();

  if (!languageSwitching || String(languageCode || 'en').toLowerCase() === 'en') {
    return null;
  }

  return (
    <View
      pointerEvents="none"
      style={{
        position: (Platform.OS === 'web' ? 'fixed' : 'absolute') as any,
        top: 12,
        right: 12,
        zIndex: 999998,
        elevation: 2,
        alignItems: 'flex-end',
        justifyContent: 'flex-start',
      }}
      data-testid="root-language-switch-overlay"
      testID="root-language-switch-overlay"
    >
      <View
        style={{
          minWidth: 220,
          maxWidth: 260,
          borderRadius: 14,
          paddingHorizontal: 14,
          paddingVertical: 12,
          backgroundColor: withAlpha(colors.surface || colors.card || colors.bgAlt || colors.bg, 'EE'),
          borderWidth: 1,
          borderColor: withAlpha(colors.primary, '2E'),
          gap: 8,
        }}
        data-testid="root-language-switch-overlay-card"
        testID="root-language-switch-overlay-card"
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <ActivityIndicator size="small" color={colors.primary} />
          <Text
            style={{ fontSize: 12, fontWeight: '700', color: colors.text }}
            data-testid="root-language-switch-overlay-text"
            testID="root-language-switch-overlay-text"
          >
            Syncing language…
          </Text>
        </View>
        <View style={{ height: 7, borderRadius: 999, backgroundColor: withAlpha(colors.primary, '24') }} />
        <View style={{ height: 7, width: '78%', borderRadius: 999, backgroundColor: withAlpha(colors.primary, '1A') }} />
      </View>
    </View>
  );
}

function ThemeAwareStack() {
  const { darkMode, colors } = useTheme();
  const { user } = useAuth();
  const pathname = usePathname();
  const isAuthenticated = !!user;
  const suppressBlockingModals = Boolean(
    pathname?.includes('employer-apply') ||
    pathname?.includes('job-platform') ||
    pathname?.includes('mini-apps/job-platform')
  );

  const screenOpts = React.useMemo(() => ({
    headerShown: false,
    animation: 'fade_from_bottom' as const,
    animationDuration: 250,
    contentStyle: { backgroundColor: isAuthenticated ? 'transparent' : colors.bg },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }), ['#050A18', isAuthenticated]); // @theme-ok dep-array-fingerprint (not a rendered color)

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg, position: 'relative' }}>
      <Stack key={darkMode ? 'dark' : 'light'} screenOptions={screenOpts}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false, animation: 'none', contentStyle: { backgroundColor: 'transparent' } }} />
      <Stack.Screen name="+not-found" options={{ headerShown: false, presentation: 'card', animation: 'fade' }} />
      <Stack.Screen name="welcome" options={{ headerShown: false, presentation: 'card', animation: 'fade' }} />
      <Stack.Screen name="auth/login" options={{ presentation: 'modal' }} />
      <Stack.Screen name="login" options={{ presentation: 'modal' }} />
      <Stack.Screen name="auth/register" options={{ presentation: 'modal' }} />
      <Stack.Screen name="auth/sso-debug" options={{ headerShown: false, presentation: 'card' }} />
      <Stack.Screen name="feature-gallery" options={{ presentation: 'modal', headerShown: false }} />
      <Stack.Screen name="job-platform" options={{ headerShown: false }} />
      <Stack.Screen name="job-platform-candidate" options={{ headerShown: false }} />
      <Stack.Screen name="job-platform-employer" options={{ headerShown: false }} />
      <Stack.Screen name="job-platform-admin" options={{ headerShown: false }} />
      <Stack.Screen name="employer-console" options={{ headerShown: false }} />
      <Stack.Screen name="career" options={{ headerShown: false }} />
      <Stack.Screen name="employer-apply" options={{ headerShown: false }} />
      <Stack.Screen name="id-verification" options={{ headerShown: false }} />
      <Stack.Screen name="id-checker" options={{ headerShown: false }} />
      <Stack.Screen name="security" options={{ headerShown: false }} />
      <Stack.Screen name="subscription/plans" options={{ headerShown: false }} />
      <Stack.Screen name="subscription/mobile-money" options={{ headerShown: false }} />
      <Stack.Screen name="subscription/mobile" options={{ headerShown: false }} />
      <Stack.Screen name="subscription/payment-result" options={{ headerShown: false }} />
      <Stack.Screen name="subscription/success" options={{ headerShown: false }} />
      <Stack.Screen name="payment-history" options={{ headerShown: false }} />
      <Stack.Screen name="my-tickets" options={{ headerShown: false }} />
      <Stack.Screen name="help" options={{ headerShown: false }} />
      <Stack.Screen name="nova-curation-hub" options={{ headerShown: false }} />
      <Stack.Screen name="about" options={{ headerShown: false }} />
      <Stack.Screen name="careers" options={{ headerShown: false }} />
      <Stack.Screen name="blog/index" options={{ headerShown: false }} />
      <Stack.Screen name="blog/[slug]" options={{ headerShown: false }} />
      <Stack.Screen name="blog/bookmarks" options={{ headerShown: false }} />
      <Stack.Screen name="press" options={{ headerShown: false }} />
      <Stack.Screen name="gdpr" options={{ headerShown: false }} />
      <Stack.Screen name="cookies" options={{ headerShown: false }} />
      <Stack.Screen name="contact" options={{ headerShown: false }} />
      <Stack.Screen name="pricing" options={{ headerShown: false }} />
      <Stack.Screen name="ai-briefing" options={{ headerShown: false }} />
      <Stack.Screen name="ai-learning-hub" options={{ headerShown: false }} />
      <Stack.Screen name="ai-problem-solver" options={{ headerShown: false }} />
      <Stack.Screen name="ai-coaching-team" options={{ headerShown: false }} />
      <Stack.Screen name="features" options={{ headerShown: false }} />
      <Stack.Screen name="mini-apps" options={{ headerShown: false }} />
      <Stack.Screen name="hiring-hub" options={{ headerShown: false }} />
      <Stack.Screen name="executive-dashboard" options={{ headerShown: false }} />
      <Stack.Screen name="notifications" options={{ headerShown: false }} />
      <Stack.Screen name="messages" options={{ headerShown: false }} />
      <Stack.Screen name="calendar" options={{ headerShown: false }} />
      <Stack.Screen name="achievements" options={{ headerShown: false }} />
      <Stack.Screen name="certificate-gallery" options={{ headerShown: false }} />
      <Stack.Screen name="certificate-operations" options={{ headerShown: false }} />
      <Stack.Screen name="leaderboard" options={{ headerShown: false }} />
      <Stack.Screen name="progress-tracker" options={{ headerShown: false }} />
      <Stack.Screen name="my-analytics" options={{ headerShown: false }} />
      <Stack.Screen name="settings" options={{ headerShown: false }} />
      <Stack.Screen name="logout" options={{ headerShown: false }} />
      <Stack.Screen name="auth/logout" options={{ headerShown: false }} />
      <Stack.Screen name="language-selector" options={{ headerShown: false }} />
      <Stack.Screen name="currency-selector" options={{ headerShown: false }} />
      <Stack.Screen name="admin" options={{ headerShown: false }} />
      <Stack.Screen name="email-templates-admin" options={{ headerShown: false }} />
      <Stack.Screen name="ai-feature-dashboard" options={{ headerShown: false }} />
      <Stack.Screen name="performance-observability" options={{ headerShown: false }} />
      <Stack.Screen name="route-health-report" options={{ headerShown: false }} />
      <Stack.Screen name="book" options={{ headerShown: false }} />
      <Stack.Screen name="team-management" options={{ headerShown: false }} />
      <Stack.Screen name="policy-console" options={{ headerShown: false }} />
      <Stack.Screen name="integrations" options={{ headerShown: false }} />
      <Stack.Screen name="verify" options={{ headerShown: false }} />
      <Stack.Screen name="certificate-verify" options={{ headerShown: false }} />
      <Stack.Screen name="certificate-verify/[verificationId]" options={{ headerShown: false }} />
      <Stack.Screen name="fps-match/index" options={{ headerShown: false }} />
      <Stack.Screen name="fps-match/[matchId]" options={{ headerShown: false }} />
      <Stack.Screen name="system-status" options={{ headerShown: false }} />
      <Stack.Screen name="content-library" options={{ headerShown: false }} />
    </Stack>
    {isAuthenticated && <FeatureQuotaPill />}
    {isAuthenticated && <SuggestedSpecialistsStrip />}
    {isAuthenticated && !suppressBlockingModals && <TosAcceptanceModal />}
    <EnterpriseMotionCoordinator />
    </View>
  );
}

function RealtimeWrapper({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  return <RealtimeProvider userId={user?.user_id || null}>{children}</RealtimeProvider>;
}

// AdminGate removed - the app is NOT admin-only.
// Admin console access is controlled by:
// 1. Backend: /api/admin/* routes require require_admin (403 for non-admins)
// 2. Frontend: AppShell only shows Admin Console sidebar link when user.is_admin
// Regular and full_access users can access the full app.
function AdminGate({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function applyDefaultFont() {
  const fontFamily = Platform.OS === 'web' ? 'Inter, system-ui, sans-serif' : 'Manrope_400Regular';
  const fontStyle = { fontFamily };
  Text.defaultProps = Text.defaultProps || {};
  Text.defaultProps.style = [Text.defaultProps.style, fontStyle];
  TextInput.defaultProps = TextInput.defaultProps || {};
  TextInput.defaultProps.style = [TextInput.defaultProps.style, fontStyle];
}

function useNonCriticalRuntimeReady() {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const triggerReady = () => {
      if (!cancelled) setReady(true);
    };

    const handle =
      Platform.OS === 'web' && typeof window !== 'undefined' && 'requestIdleCallback' in window
        ? (window as any).requestIdleCallback(triggerReady, { timeout: 1200 })
        : setTimeout(triggerReady, 450);

    return () => {
      cancelled = true;
      if (Platform.OS === 'web' && typeof window !== 'undefined' && 'cancelIdleCallback' in window && typeof handle !== 'number') {
        (window as any).cancelIdleCallback(handle);
      }
      if (typeof handle === 'number') {
        clearTimeout(handle);
      }
    };
  }, []);

  return ready;
}

type BootPolicyState = {
  ready: boolean;
  blocked: boolean;
  reason: string;
  policyId: string;
  attempts: number;
};

function useBootPolicyHandshakeState() {
  const [state, setState] = useState<BootPolicyState>({
    ready: Platform.OS !== 'web',
    blocked: false,
    reason: 'native',
    policyId: '',
    attempts: 0,
  });

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    const apply = (payload: any) => {
      if (!payload || typeof payload !== 'object') return;
      setState({
        ready: Boolean(payload.ready),
        blocked: Boolean(payload.blocked),
        reason: String(payload.reason || ''),
        policyId: String(payload.policyId || ''),
        attempts: Number(payload.attempts || 0),
      });
    };

    try {
      apply((window as any).__racBootPolicyState);
    } catch (error) {
      handleAppRecoverableError({
        scope: '_layout.tsx#catch2',
        error,
        message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
    }

    const handler = (evt: Event) => {
      const detail = (evt as CustomEvent).detail;
      apply(detail);
    };
    window.addEventListener('rac:boot-policy-ready', handler as EventListener);

    const fallback = setTimeout(() => {
      setState((prev) => {
        if (prev.ready || prev.blocked) return prev;
        return { ...prev, ready: true, reason: prev.reason || 'bootstrap_timeout' };
      });
    }, 6500);

    return () => {
      window.removeEventListener('rac:boot-policy-ready', handler as EventListener);
      clearTimeout(fallback);
    };
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!state.blocked || state.reason !== 'max_reload_attempts_exceeded') return;

    try {
      if ((window as any).__racBootPolicyShouldReloadTelemetrySent) return;
      (window as any).__racBootPolicyShouldReloadTelemetrySent = true;

      const payload = {
        event_type: 'should_reload_true',
        policy_id: String(state.policyId || ''),
        route_path: String(window.location.pathname || ''),
        route_query: String(window.location.search || ''),
        host: String(window.location.hostname || ''),
        source: 'layout_blocked_fallback',
        reason: 'max_reload_attempts_exceeded',
        reload_attempt: Number(state.attempts || 0),
      };

      const body = JSON.stringify(payload);
      if (typeof navigator !== 'undefined' && 'sendBeacon' in navigator && typeof Blob !== 'undefined') {
        const blob = new Blob([body], { type: 'application/json' });
        (navigator as any).sendBeacon('/api/config/boot-policy/telemetry', blob);
        return;
      }

      fetch('/api/config/boot-policy/telemetry', {
        method: 'POST',
        credentials: 'omit',
        cache: 'no-store',
        keepalive: true,
        headers: { 'Content-Type': 'application/json' },
        body,
      }).catch(() => {});
    } catch (error) {
      handleAppRecoverableError({
        scope: '_layout.tsx#catch3',
        error,
        message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      });
    }
  }, [state.blocked, state.reason, state.policyId, state.attempts]);

  return state;
}

function BootPolicyBlockedFallback({ reason, policyId }: { reason: string; policyId: string }) {
  const fallbackColors = {
    textSec: 'var(--app-warning)',
    textMuted: 'var(--app-text-muted)',
    accent: 'var(--app-primary)',
    border: 'var(--app-warning-soft)',
    surface: 'var(--app-card-muted)',
    buttonText: 'var(--app-primary-text)',
  };
  return (
    <View
      style={{
        marginHorizontal: 12,
        marginTop: 8,
        marginBottom: 6,
        borderWidth: 1,
        borderColor: fallbackColors.border as any,
        borderRadius: 10,
        backgroundColor: fallbackColors.surface as any,
        paddingHorizontal: 12,
        paddingVertical: 10,
        gap: 8,
      }}
      data-testid="boot-policy-blocked-fallback"
      testID="boot-policy-blocked-fallback"
    >
      <Text style={{ color: fallbackColors.textSec, fontSize: 13, fontWeight: '900' }} data-testid="boot-policy-blocked-title" testID="boot-policy-blocked-title">
        Startup guardrails entered degraded mode
      </Text>
      <Text style={{ color: fallbackColors.textMuted, fontSize: 11, lineHeight: 16 }} data-testid="boot-policy-blocked-reason" testID="boot-policy-blocked-reason">
        Startup handshake is degraded. Platform access is still available using fallback mode while the guardrail recovers.
      </Text>
      <Text style={{ color: fallbackColors.textMuted, fontSize: 10 }} data-testid="boot-policy-blocked-meta" testID="boot-policy-blocked-meta">
        Reason: {reason || 'unknown'}{policyId ? ` · Policy: ${policyId}` : ''}
      </Text>
      <TouchableOpacity
        onPress={() => {
          if (Platform.OS === 'web' && typeof window !== 'undefined') window.location.reload();
        }}
        style={{
          marginTop: 4,
          backgroundColor: fallbackColors.accent,
          alignSelf: 'flex-start',
          borderRadius: 8,
          paddingHorizontal: 12,
          paddingVertical: 8,
        }}
        data-testid="boot-policy-blocked-reload-button"
        testID="boot-policy-blocked-reload-button"
      >
        <Text style={{ color: fallbackColors.buttonText as any, fontSize: 11, fontWeight: '800' }}>Retry startup handshake</Text>
      </TouchableOpacity>
    </View>
  );
}

function RootLoadingFallback() {
  // Uses CSS variables so loading fallback still follows active theme tokens.
  const fallbackColors = { textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)' };
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: 'var(--app-bg)' as any,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 24,
      }}
      data-testid="root-loading-fallback" testID="root-loading-fallback"
    >
      <View style={{ width: 88, height: 88, borderRadius: 26, backgroundColor: (globalThis as any).__alphaColor('var(--app-primary)', '1F'), alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: (globalThis as any).__alphaColor('var(--app-primary)', '3D') }}>
        <ActivityIndicator size="large" color={'var(--app-primary)'} />
      </View>
      <Text style={{ color: fallbackColors.textSec, fontSize: 18, fontWeight: '800', marginTop: 18, textAlign: 'center' }} data-testid="root-loading-fallback-title" testID="root-loading-fallback-title">
        RealAICoach is preparing your workspace
      </Text>
      <Text style={{ color: fallbackColors.textMuted, fontSize: 13, lineHeight: 20, marginTop: 8, textAlign: 'center', maxWidth: 340 }} data-testid="root-loading-fallback-copy" testID="root-loading-fallback-copy">
        Loading safely with cache recovery and route guardrails so the app never drops to a blank screen.
      </Text>
    </View>
  );
}

ensureGlobalAlphaColor();

export default function RootLayout() {

  const [hydrated, setHydrated] = useState(false);
  const storeHydrated = useAppStore((state) => state._hasHydrated || state.hasHydrated);
  const nonCriticalRuntimeReady = useNonCriticalRuntimeReady();
  const bootPolicyState = useBootPolicyHandshakeState();

  ensureGlobalAlphaColor();

  useEffect(() => { setHydrated(true); }, []);

  // P1-07: Removed blocking full-screen CSS overlay.
  // Language switching now uses only the non-blocking GlobalLanguageSwitchOverlay component
  // (positioned at top-right corner with pointerEvents: none).

  const [nativeFontsLoaded] = useFonts(
    Platform.OS !== 'web' ? {
      Manrope_400Regular,
      Manrope_500Medium,
      Manrope_600SemiBold,
      Manrope_700Bold,
      Manrope_800ExtraBold,
    } : {}
  );

  const fontsReady = Platform.OS === 'web' ? true : nativeFontsLoaded;

  useEffect(() => {
    if (fontsReady && hydrated && storeHydrated) {
      applyDefaultFont();
      SplashScreen.hideAsync();
      if (Platform.OS === 'web' && typeof document !== 'undefined') {
        const root = document.getElementById('root');
        if (root) root.setAttribute('data-app-ready', 'true');
      }
    }
  }, [fontsReady, hydrated, storeHydrated]);

  useEffect(() => {
    if (!fontsReady || !hydrated || !storeHydrated) return;
    const runClear = () => {
      void clearLegacyCachesOnce();
    };

    const handle =
      Platform.OS === 'web' && typeof window !== 'undefined' && 'requestIdleCallback' in window
        ? (window as any).requestIdleCallback(runClear, { timeout: 1600 })
        : setTimeout(runClear, 500);

    return () => {
      if (Platform.OS === 'web' && typeof window !== 'undefined' && 'cancelIdleCallback' in window && typeof handle !== 'number') {
        (window as any).cancelIdleCallback(handle);
      }
      if (typeof handle === 'number') {
        clearTimeout(handle);
      }
    };
  }, [fontsReady, hydrated, storeHydrated]);

  if (!fontsReady || !hydrated || !storeHydrated) {
    return <RootLoadingFallback />;
  }

  if (!bootPolicyState.ready && !bootPolicyState.blocked) {
    return <RootLoadingFallback />;
  }

  return (
    <ErrorBoundary>
    <SafeAreaProvider>
      <SkipToContentComp />
      <LiveRegionComp />
      <ConfigProvider>
        <AuthProvider>
          <AccessControlProvider>
          <SubscriptionProvider>
          <RealtimeWrapper>
          <FeaturesProvider>
          <ThemeProvider>
            <GlobalLanguageSwitchOverlay />
            <AccessibilityWrapper>
            <LocationProvider>
            <LanguageProvider>
            <GLSProvider>
            <GlobalTranslationProvider>
            <BackgroundBrightnessProvider>
              {nonCriticalRuntimeReady && <PushNotificationRegistrar />}
              <PreviewHealthReporter />
              {nonCriticalRuntimeReady && <WebVitalsReporter />}
              {nonCriticalRuntimeReady && <UiRouteGuardReporter />}
              {nonCriticalRuntimeReady && <RealtimeToast />}
              {nonCriticalRuntimeReady && <SafeUpdateBanner />}
              {nonCriticalRuntimeReady && <StartupRecoveryBanner />}
              {nonCriticalRuntimeReady && <PreviewHostRecoveryBanner />}
              {nonCriticalRuntimeReady && <PreviewShellMismatchBanner />}
              {nonCriticalRuntimeReady && <GlobalWhiteScreenGuard />}
              {bootPolicyState.blocked && <BootPolicyBlockedFallback reason={bootPolicyState.reason} policyId={bootPolicyState.policyId} />}
              <GpsDegradedGlobalBanner />
              <OfflineBanner />
              <RealtimeReconnectBanner />
              <ThemeAwareStatusBar />
              <ThemeEnforcer />
              <UIEMProvider>
              <UIEMWatchdog>
              <ErrorBoundary>
              {nonCriticalRuntimeReady && <SubscriptionUpgradeModal />}
              <GlobalMaintenanceOverlay />
              <RouteAccessGuard />
              <MiniAppRouteRedirector />
              <ThemeComplianceRuntimeGate>
                <AdminGate>
                  <ThemeAwareStack />
                  <GlobalPlatformRouteGuard />
                  {nonCriticalRuntimeReady && <PWAInstallBanner />}
                  {nonCriticalRuntimeReady && <RouteAnnouncer />}
                </AdminGate>
              </ThemeComplianceRuntimeGate>
              <WhatsNewRootPortal />
              </ErrorBoundary>
              </UIEMWatchdog>
              </UIEMProvider>
            </BackgroundBrightnessProvider>
            </GlobalTranslationProvider>
            </GLSProvider>
            </LanguageProvider>
            </LocationProvider>
            </AccessibilityWrapper>
          </ThemeProvider>
          </FeaturesProvider>
          </RealtimeWrapper>
          </SubscriptionProvider>
          </AccessControlProvider>
        </AuthProvider>
      </ConfigProvider>
    </SafeAreaProvider>
    </ErrorBoundary>
  );
}