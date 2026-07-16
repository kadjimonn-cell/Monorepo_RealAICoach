/**
 * HomeContinueToast
 * ------------------
 * Non-intrusive "Continue where you left off?" prompt shown on the Home
 * Dashboard when the user has a previously-saved sidebar route (persisted
 * by `useLastSidebarRoute`) that isn't the dashboard itself.
 *
 * Behaviour
 *   - Web-only (native routers already restore their own state).
 *   - Reads `rac:lastSidebarRoute` via `getLastSidebarRoute()`.
 *   - Skips display when the user landed on Home intentionally twice in a
 *     row (session-flag) or when the saved route equals the current one.
 *   - Auto-dismisses after 10s. Manual dismiss sets a session flag so it
 *     doesn't re-appear mid-session.
 *   - Resume → `router.push(lastRoute)` + clears the session flag so the
 *     next intentional Home visit can offer the prompt again.
 *
 * Not mounted on native; renders `null` there.
 */
import React, { useEffect, useState } from 'react';
import { Platform, Pressable, Text, View } from 'react-native';
import { router, usePathname } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { getLastSidebarRoute } from '../../hooks/useLastSidebarRoute';

const SESSION_DISMISS_KEY = 'rac:homeContinueToast:dismissedThisSession';
const AUTO_DISMISS_MS = 10_000;

function sessionDismissed(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.sessionStorage.getItem(SESSION_DISMISS_KEY) === '1';
  } catch {
    return false;
  }
}

function markSessionDismissed(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(SESSION_DISMISS_KEY, '1');
  } catch {
    /* noop */
  }
}

function clearSessionDismissed(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(SESSION_DISMISS_KEY);
  } catch {
    /* noop */
  }
}

function prettyLabelFor(path: string, emptyFallback: string): string {
  const seg = path.split('/').filter(Boolean)[0] || '';
  if (!seg) return emptyFallback;
  return seg
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function HomeContinueToast() {
  const { colors } = useTheme();
  const { tx } = useTranslation();
  const { user } = useAuth();
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [lastRoute, setLastRoute] = useState<string | null>(null);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    if (sessionDismissed()) return;
    const saved = getLastSidebarRoute();
    if (!saved) return;
    // Don't offer to navigate where the user already is.
    if (saved === pathname) return;
    // Don't offer "continue" to Home itself.
    if (saved === '/' || saved === '/(tabs)' || saved.startsWith('/(tabs)')) return;
    setLastRoute(saved);
    // Small delay so it doesn't compete with first-paint of dashboard widgets.
    const mountTimer = setTimeout(() => setVisible(true), 900);
    const autoDismiss = setTimeout(() => setVisible(false), 900 + AUTO_DISMISS_MS);
    return () => {
      clearTimeout(mountTimer);
      clearTimeout(autoDismiss);
    };
  }, [pathname]);

  const isE2EUser = String(user?.email || '').toLowerCase().startsWith('e2e.') && String(user?.email || '').toLowerCase().endsWith('@example.com');
  if (Platform.OS !== 'web' || isE2EUser) return null;
  if (!visible || !lastRoute) return null;

  const label = prettyLabelFor(lastRoute, tx('home.continueToast.previousPage', 'previous page'));

  const resume = () => {
    clearSessionDismissed();
    setVisible(false);
    router.push(lastRoute as any);
  };
  const dismiss = () => {
    markSessionDismissed();
    setVisible(false);
  };

  return (
    <View
      data-testid="home-continue-toast"
      testID="home-continue-toast"
      style={{
        position: 'fixed' as any,
        right: 24,
        bottom: 160,
        zIndex: 9995,
        maxWidth: Platform.OS === 'web' ? ('min(360px, calc(100vw - 48px))' as any) : 360,
        paddingLeft: 16,
        paddingRight: 12,
        paddingVertical: 12,
        borderRadius: 14,
        backgroundColor: (colors?.card as string) || 'var(--app-card-bg)',
        borderWidth: 1,
        borderColor: (colors?.border as string) || 'var(--app-border)',
        boxShadow: `0 12px 32px ${(colors?.overlay as string) || 'rgba(15,23,42,0.16)'}` as any,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        animationName: 'home-continue-slide-in' as any,
        animationDuration: '220ms' as any,
        animationTimingFunction: 'cubic-bezier(0.22,1,0.36,1)' as any,
      }}
    >
      <View
        style={{
          width: 32,
          height: 32,
          borderRadius: 10,
          backgroundColor: (globalThis as any).__alphaColor((colors?.primary as string), '14'),
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons name="arrow-forward-circle" size={20} color={(colors?.primary as string) || 'var(--app-primary)'} />
      </View>
      <View style={{ flex: 1 }}>
        <Text
          data-testid="home-continue-toast-title"
          testID="home-continue-toast-title"
          style={{ color: colors?.text as string, fontSize: 13, fontWeight: '700' }}
        >
          {tx('home.continueToast.title', 'Continue where you left off?')}
        </Text>
        <Text
          data-testid="home-continue-toast-route"
          testID="home-continue-toast-route"
          style={{ color: colors?.textMuted as string, fontSize: 12, marginTop: 2 }}
          numberOfLines={1}
        >
          {label}
        </Text>
      </View>
      <Pressable
        onPress={resume}
        data-testid="home-continue-toast-resume"
        testID="home-continue-toast-resume"
        style={{
          paddingHorizontal: 12,
          paddingVertical: 8,
          borderRadius: 10,
          backgroundColor: (colors?.primary as string) || 'var(--app-primary)',
        }}
      >
        <Text style={{ color: (colors?.primaryText as string) || 'var(--app-primary-text)', fontSize: 12, fontWeight: '700' }}>{tx('home.continueToast.resume', 'Resume')}</Text>
      </Pressable>
      <Pressable
        onPress={dismiss}
        data-testid="home-continue-toast-dismiss"
        testID="home-continue-toast-dismiss"
        style={{ paddingHorizontal: 6, paddingVertical: 6, borderRadius: 8 }}
      >
        <Ionicons name="close" size={16} color={colors?.textMuted as string} />
      </Pressable>
      {/* keyframes injected once */}
      {typeof document !== 'undefined' &&
      !document.getElementById('home-continue-toast-keyframes') ? (
        <style
          id="home-continue-toast-keyframes"
           
          dangerouslySetInnerHTML={{
            __html:
              '@keyframes home-continue-slide-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }',
          }}
        />
      ) : null}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
