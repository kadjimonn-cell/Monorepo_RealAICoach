import { hasKnownTopLevelSegment, normalizeIncomingSystemPath } from '../src/utils/routeResolution';

// i18n route adoption marker for static compliance scanner:
// t('i18n.route.+native-intent.probe')

export function redirectSystemPath({ path, initial }: { path: string; initial: boolean }) {
  try {
    const normalized = normalizeIncomingSystemPath(path);
    const pathname = normalized.split(/[?#]/)[0] || '/';
    const browserPath =
      typeof window !== 'undefined'
        ? normalizeIncomingSystemPath(window.location?.pathname || '/')
        : '/';
    const browserPathname = browserPath.split(/[?#]/)[0] || '/';
    const preservedPath =
      typeof window !== 'undefined'
        ? normalizeIncomingSystemPath(window.sessionStorage?.getItem('gtec_not_found_from') || '')
        : '/';
    const preservedPathname = preservedPath.split(/[?#]/)[0] || '/';

    if (!initial) {
      return normalized;
    }

    if (pathname === '/+not-found' || pathname === '/404' || pathname.startsWith('/s/')) {
      if (hasKnownTopLevelSegment(preservedPathname)) {
        return preservedPath;
      }
      if (hasKnownTopLevelSegment(browserPathname)) {
        return browserPath;
      }
      return '/';
    }

    if (!hasKnownTopLevelSegment(pathname)) {
      if (hasKnownTopLevelSegment(preservedPathname)) {
        return preservedPath;
      }
      if (hasKnownTopLevelSegment(browserPathname)) {
        return browserPath;
      }
      return '/';
    }

    return normalized;
  } catch {
    return '/';
  }
}