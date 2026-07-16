/**
 * Last-sidebar-route persistence (web-only).
 *
 * Remembers the most recent known sidebar route the user visited (writes
 * on every `usePathname()` change) and exposes a getter/clearer for the
 * root index redirect + logout flow. This way, refreshing the browser
 * from any inside-page (or opening a new tab to `/` mid-session) lands
 * the user back exactly where they were instead of dumping them on the
 * Home dashboard.
 *
 * Scope rules (kept deliberately narrow so we never restore into a
 * route the user never truly intended to stay on):
 *   - Only paths whose first segment is in KNOWN_TOP_LEVEL_SEGMENTS
 *     are saved (typo routes and +not-found are skipped).
 *   - A small block-list of "transient" routes (auth flows, welcome,
 *     dashboard alias, marketing/public pages, raw `/`) is never saved.
 *   - localStorage only (web). No-op on native — native routers already
 *     restore their own state.
 */
import { useEffect } from 'react';
import { Platform } from 'react-native';
import { usePathname } from 'expo-router';
import { hasKnownTopLevelSegment, getFirstRouteSegment } from '../utils/routeResolution';

const STORAGE_KEY = 'rac:lastSidebarRoute';

// Routes that should NEVER be persisted — either they're transient
// bootstrapping states (auth, welcome) or they'd re-trigger the very
// redirect loop we're trying to avoid.
const NEVER_PERSIST_SEGMENTS = new Set<string>([
  '', // bare '/'
  'auth',
  'welcome',
  'dashboard', // alias that redirects to /(tabs) -> / anyway
  '+not-found',
  '404',
  'legal-pages',
  'terms',
  'privacy',
  'cookies',
  'contact',
  'blog',
  's', // short-link handler
  '_sitemap',
  'mini-apps', // these have their own redirector
]);

function shouldPersist(pathname: string): boolean {
  if (!pathname || pathname === '/') return false;
  if (!hasKnownTopLevelSegment(pathname)) return false;
  const seg = getFirstRouteSegment(pathname);
  if (NEVER_PERSIST_SEGMENTS.has(seg)) return false;
  return true;
}

export function getLastSidebarRoute(): string | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (!v) return null;
    // Re-validate before returning so a renamed route or deleted
    // permission doesn't strand the user on a dead path.
    if (!hasKnownTopLevelSegment(v)) return null;
    return v;
  } catch {
    return null;
  }
}

export function clearLastSidebarRoute(): void {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* noop */
  }
}

/**
 * Side-effect hook: subscribes to `usePathname()` and writes the current
 * path to localStorage whenever it points to a savable sidebar route.
 * Mount this once (AppShell is the natural place — it wraps every
 * authenticated sidebar page).
 */
export function useTrackLastSidebarRoute(): void {
  const pathname = usePathname();
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;
    if (!pathname || !shouldPersist(pathname)) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, pathname);
    } catch {
      /* storage may be blocked — silently ignore */
    }
  }, [pathname]);
}

// Re-export the key only for tests/debug. Not part of the runtime API.
export const __STORAGE_KEY_FOR_TESTS = STORAGE_KEY;
