import React, { useEffect, useState } from 'react';
import { Stack, useRouter, usePathname } from 'expo-router';
import { StyleSheet, View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { recordShellHealthMetric } from '../src/services/shellHealthMonitor';
import { hasKnownTopLevelSegment } from '../src/utils/routeResolution';
import { suggestNearestPublicPath } from '../src/utils/suggestNearestPublicPath';
import { handleAppRecoverableError } from '../src/utils/appRecoverableError';
import LanguageContext from '../src/i18n/LanguageContext';

import { useAdminTheme } from '../src/hooks/useAdminTheme';
import { useAuth } from '../src/context/AuthContext';
import { ProtectedRouteGate } from '../src/components/auth/ProtectedRouteGate';
const KPI_SLUGS = new Set(['streak', 'active', 'complete', 'minutes']);

export default function NotFoundScreen() {
  const { isAuthenticated, loading: authLoading } = useAuth();
  const AC = useAdminTheme();
  const languageContext = React.useContext(LanguageContext as any);
  const router = useRouter();
  const pathname = usePathname();
  const [countdown, setCountdown] = useState(5);
  // "Did you mean …?" helper — reads the mistyped path preserved by
  // serve-production.js in sessionStorage and suggests the nearest
  // PUBLIC route (Levenshtein, threshold ≤ 3). Turns the dead-end into
  // a one-click recovery for typos like `/feature-galery` →
  // `/feature-gallery`, `/prvacy-policy` → `/privacy-policy`.
  const [suggestion, setSuggestion] = useState<{ from: string; to: string } | null>(null);
  // Re-create the StyleSheet from the LIVE theme so this page respects the
  // user's selected light/dark mode (previously used a module-level
  // `getAdminColors(true)` which pinned the styles to dark forever).
  const styles = React.useMemo(() => makeStyles(AC), [AC]);
  const tx = React.useCallback((key: string, fallback: string) => {
    try {
      const translated = languageContext?.t?.(key);
      if (!translated || translated === key) return fallback;
      return translated;
    } catch {
      return fallback;
    }
  }, [languageContext]);

  const titleText = tx('notFound.title', 'Page Not Found');
  const subtitleText = tx('notFound.subtitle', "The page you're looking for doesn't exist or has been moved.");
  const didYouMeanText = tx('notFound.didYouMean', 'Did you mean');
  const countdownTemplate = tx('notFound.redirectingHome', 'Redirecting to home in {countdown}s...');
  const goHomeText = tx('notFound.goHome', 'Go Home Now');

  // Track the pathname at mount so the auto-redirect can abort if the
  // user navigates to a valid route before the countdown fires. This fixes
  // a subtle bug where Expo Router briefly mounts `+not-found` during
  // client-side route resolution on hard refreshes of slower-to-hydrate
  // routes (/book-meeting, /referrals, /settings, ...). The component
  // then unmounts once the real route registers, but the interval was
  // still running and fired `router.replace('/')` — sending users who
  // refreshed any inside-page back to the Home dashboard. The guard
  // below checks the CURRENT pathname on every tick and cancels the
  // redirect if the app has since navigated to a known route.
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const path = window.location.pathname || '';
      let preservedNotFoundPath = '';
      try {
        preservedNotFoundPath = (typeof sessionStorage !== 'undefined'
          && sessionStorage.getItem('gtec_not_found_from')) || '';
      } catch (error) {
        handleAppRecoverableError({
          scope: 'not-found.read-preserved-path',
          error,
          message: 'Could not read route recovery state.',
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      }
      if (path === '/id-checker') {
        recordShellHealthMetric('route_recoveries', { mode: 'id_checker_alias_redirect', reason: 'route_alias' });
        const search = window.location.search || '';
        router.replace((`/id-verification${search}`) as any);
        return;
      }
      const match = path.match(/^\/ai-learning-hub\/kpi\/([^/]+)$/i);
      const slug = match?.[1]?.toLowerCase?.() || '';
      if (slug && KPI_SLUGS.has(slug)) {
        recordShellHealthMetric('route_recoveries', { mode: 'kpi_route_redirect', reason: 'not_found_alias' });
        router.replace(`/ai-learning-hub-kpi/${slug}` as any);
        return;
      }

      const certificatePath = preservedNotFoundPath || path;
      const certificateMatch = certificatePath.match(/^\/certificate-verify\/([^/?#]+)\/?$/i);
      const certificateId = certificateMatch?.[1] ? decodeURIComponent(certificateMatch[1]) : '';
      if (certificateId) {
        recordShellHealthMetric('route_recoveries', { mode: 'certificate_verify_static_fallback', reason: 'not_found_alias' });
        router.replace(`/certificate-verify?verificationId=${encodeURIComponent(certificateId)}` as any);
        return;
      }

      const fpsMatchMatch = certificatePath.match(/^\/fps-match\/([^/?#]+)\/?$/i);
      const fpsMatchId = fpsMatchMatch?.[1] ? decodeURIComponent(fpsMatchMatch[1]) : '';
      if (fpsMatchId) {
        recordShellHealthMetric('route_recoveries', { mode: 'fps_match_static_fallback', reason: 'not_found_alias' });
        router.replace(`/fps-match?matchId=${encodeURIComponent(fpsMatchId)}` as any);
        return;
      }

      const legacyOfferMatch = certificatePath.match(/^\/admin\/offers\/([^/?#]+)\/?$/i);
      const legacyOfferId = legacyOfferMatch?.[1] ? decodeURIComponent(legacyOfferMatch[1]) : '';
      if (legacyOfferId) {
        recordShellHealthMetric('route_recoveries', {
          mode: 'admin_offer_studio_legacy_alias',
          reason: 'not_found_alias',
          pathname: certificatePath,
        });
        router.replace(`/admin/offer-studio?offerId=${encodeURIComponent(legacyOfferId)}` as any);
        return;
      }

      // "Did you mean …?" — read the preserved mistyped path from
      // sessionStorage (set by serve-production.js before JS hydrates)
      // and compute the nearest public route via Levenshtein distance.
      try {
        const from = (typeof sessionStorage !== 'undefined'
          && sessionStorage.getItem('gtec_not_found_from')) || '';
        if (from) {
          const to = suggestNearestPublicPath(from);
          if (to && to !== from) {
            setSuggestion({ from, to });
            recordShellHealthMetric('route_recoveries', {
              mode: 'did_you_mean_offered', reason: 'not_found',
              pathname: from, suggested: to,
            });
          }
        }
      } catch (error) {
        handleAppRecoverableError({
          scope: 'not-found.did-you-mean-helper',
          error,
          message: 'Could not compute route suggestion.',
          onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
        
        notifyMode: 'dialog',
        userInitiated: true,
      });
      }
    }

    const timer = setInterval(() => {
      // Abort the auto-redirect if the app has already routed the user
      // to a real page behind us (React Native Web's router often
      // mounts +not-found for a beat while a route bundle loads — we
      // must not drag the user to `/` after their real route resolves).
      const currentPath = (typeof window !== 'undefined' && window.location?.pathname) || pathname || '';
      let preservedPath = '';
      try {
        preservedPath = (typeof sessionStorage !== 'undefined' && sessionStorage.getItem('gtec_not_found_from')) || '';
      } catch {
        preservedPath = '';
      }
      const preservedIsFeaturePath = preservedPath === '/features' || preservedPath.startsWith('/features/');
      const hasRecoverablePreservedPath = !!preservedPath && hasKnownTopLevelSegment(preservedPath) && preservedPath !== currentPath;
      if (hasRecoverablePreservedPath) {
        clearInterval(timer);
        recordShellHealthMetric('route_recoveries', {
          mode: 'preserved_path_recover',
          reason: 'not_found_transient',
          pathname: currentPath,
          suggested: preservedPath,
        });
        router.replace(preservedPath as any);
        return;
      }

      if (preservedIsFeaturePath) {
        clearInterval(timer);
        recordShellHealthMetric('route_recoveries', {
          mode: 'feature_route_preserve',
          reason: 'not_found_transient',
          pathname: currentPath,
          suggested: preservedPath,
        });
        return;
      }

      const stillOnNotFound = !currentPath || !hasKnownTopLevelSegment(currentPath);
      if (!stillOnNotFound) {
        clearInterval(timer);
        recordShellHealthMetric('route_recoveries', { mode: 'auto_redirect_cancelled', reason: 'resolved_to_known_route', pathname: currentPath });
        return;
      }
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timer);
          recordShellHealthMetric('route_recoveries', { mode: 'auto_redirect_paused', reason: 'not_found', pathname: currentPath });
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
    // Intentionally depend on `pathname` so the interval is reset whenever
    // Expo Router hands us a new path — the effect cleanup clears the
    // stale interval and the new one reads the fresh pathname.
  }, [router, pathname]);

  return (
    <ProtectedRouteGate isLoading={authLoading} isAllowed={isAuthenticated} returnTo={pathname || '/dashboard'}>
      <>
        <Stack.Screen options={{ title: titleText }} />
        <View style={styles.container} data-testid="not-found-screen" testID="not-found-screen">
          <View style={styles.card}>
            <View style={styles.iconWrap}>
              <Ionicons name="compass-outline" size={40} color={AC.accent} />
            </View>
            <Text style={styles.title}>{titleText}</Text>
            <Text style={styles.subtitle}>{subtitleText}</Text>
            {suggestion ? (
              <TouchableOpacity
                style={styles.suggestionChip}
                onPress={() => {
                  recordShellHealthMetric('route_recoveries', {
                    mode: 'did_you_mean_clicked', reason: 'not_found',
                    pathname: suggestion.from, suggested: suggestion.to,
                  });
                  // Clear the preserved path so it doesn't resurface on the
                  // next unrelated 404 in the same session.
                  try {
                    if (typeof sessionStorage !== 'undefined') {
                      sessionStorage.removeItem('gtec_not_found_from');
                    }
                  } catch (error) {
                    handleAppRecoverableError({
                      scope: 'not-found.clear-preserved-path',
                      error,
                      message: 'Could not clear preserved route state.',
                      onRetry: () => { if (typeof window !== 'undefined') window.location.reload(); },
                    
          notifyMode: 'dialog',
          userInitiated: true,
        });
                  }
                  router.replace(suggestion.to as any);
                }}
                data-testid="not-found-did-you-mean-btn"
                testID="not-found-did-you-mean-btn"
                accessibilityRole="button"
                accessibilityLabel={`${didYouMeanText} ${suggestion.to}?`}
              >
                <Ionicons name="sparkles-outline" size={14} color={AC.primary} />
                <Text style={styles.suggestionText}>
                  {didYouMeanText}{' '}
                  <Text style={styles.suggestionTextStrong}>{suggestion.to}</Text>
                  ?
                </Text>
              </TouchableOpacity>
            ) : null}
            <Text style={styles.countdown}>
              {countdownTemplate.replace('{countdown}', String(countdown))}
            </Text>
            <TouchableOpacity
              style={styles.btn}
              onPress={() => {
                recordShellHealthMetric('route_recoveries', { mode: 'manual_redirect', reason: 'not_found' });
                router.replace('/');
              }}
              data-testid="not-found-go-home-btn" testID="not-found-go-home-btn"
              accessibilityRole="button"
            >
              <Ionicons name="home-outline" size={18} color="#050A18" /> {/* @theme-ok button-icon-on-fixed-accent-bg */}
              <Text style={styles.btnText}>{goHomeText}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </>
    </ProtectedRouteGate>
  );
}

const makeStyles = (AC: ReturnType<typeof useAdminTheme>) => StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
    backgroundColor: AC.bg,
  },
  card: {
    maxWidth: 420,
    width: '100%',
    backgroundColor: AC.card,
    borderRadius: 22,
    padding: 40,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: AC.border,
  },
  iconWrap: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: AC.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 20,
  },
  title: {
    color: AC.text,
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 10,
    letterSpacing: -0.3,
  },
  subtitle: {
    color: AC.textMuted,
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
    marginBottom: 16,
  },
  countdown: {
    color: AC.textDim,
    fontSize: 13,
    marginBottom: 20,
  },
  suggestionChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: AC.primarySoft,
    borderWidth: 1,
    borderColor: AC.primary,
    paddingVertical: 9,
    paddingHorizontal: 14,
    borderRadius: 999,
    marginBottom: 18,
    alignSelf: 'center',
  },
  suggestionText: {
    color: AC.text,
    fontSize: 13,
    lineHeight: 18,
  },
  suggestionTextStrong: {
    color: AC.primary,
    fontWeight: '800',
  },
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: AC.primary,
    paddingVertical: 14,
    paddingHorizontal: 32,
    borderRadius: 12,
    width: '100%',
  },
  btnText: {
    color: AC.primaryText,
    fontSize: 14,
    fontWeight: '700',
  },
});
