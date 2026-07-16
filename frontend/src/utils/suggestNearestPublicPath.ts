/**
 * suggestNearestPublicPath — "Did you mean …?" helper for the Page Not
 * Found card. Takes the mistyped path the visitor hit (preserved in
 * `sessionStorage.gtec_not_found_from` by serve-production.js) and
 * returns the closest PUBLIC route, or null if nothing's close enough.
 *
 * Scope: only suggest routes that are reachable without authentication.
 * We intentionally omit auth-gated routes like /book-meeting even though
 * they exist — suggesting them would turn one dead-end (wrong URL) into
 * another (login bounce), which hurts anonymous-visitor UX.
 *
 * Algorithm: classic Levenshtein distance against the first path
 * segment, plus a small prefix-aware bonus so `/feature-galery` matches
 * `/feature-gallery` tightly. Threshold 3 for segments ≤ 8 chars and
 * (len/3 + 1) for longer segments, so we don't suggest wildly unrelated
 * routes on short typos.
 */

// Kept in sync with RouteAccessGuard.PUBLIC_EXACT_ROUTES (Apr 22 2026).
// The regression guard `test_route_access_guard_public_paths.py` locks
// this in.
const PUBLIC_PATHS: readonly string[] = [
  '/',
  '/welcome',
  '/login',
  '/about',
  '/about-us',
  '/blog',
  '/careers',
  '/talent-network',
  '/certificate-compare',
  '/contact',
  '/cookies',
  '/faq',
  '/feature-gallery',
  '/gdpr',
  '/help',
  '/invite-accept',
  '/press',
  '/pricing',
  '/privacy-policy',
  '/privacy-request',
  '/privacy-verify',
  '/security',
  '/terms',
  '/track-application',
  '/verify',
];

function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const prev = new Array(b.length + 1);
  const curr = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(
        curr[j - 1] + 1,
        prev[j] + 1,
        prev[j - 1] + cost,
      );
    }
    for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
  }
  return prev[b.length];
}

export function suggestNearestPublicPath(fromPath: string | null | undefined): string | null {
  if (!fromPath) return null;
  const cleaned = fromPath.split(/[?#]/)[0].toLowerCase().trim();
  if (!cleaned || cleaned === '/' || cleaned.length > 120) return null;
  // Reject paths that are already public — nothing to suggest.
  if (PUBLIC_PATHS.includes(cleaned)) return null;

  const firstSeg = cleaned.replace(/^\/+/, '').split('/')[0];
  if (!firstSeg || firstSeg.length < 2) return null;

  const threshold = firstSeg.length <= 8
    ? 3
    : Math.floor(firstSeg.length / 3) + 1;

  let best: { path: string; dist: number } | null = null;
  for (const candidate of PUBLIC_PATHS) {
    if (candidate === '/') continue;
    const candSeg = candidate.replace(/^\/+/, '').split('/')[0];
    const dist = levenshtein(firstSeg, candSeg);
    // Prefix bonus — "feature-galery" should win against "feature-gallery"
    // even if the raw distance is tied with an unrelated short word.
    const prefixBonus = (firstSeg.startsWith(candSeg.slice(0, 3)) || candSeg.startsWith(firstSeg.slice(0, 3))) ? -0.5 : 0;
    const adjusted = dist + prefixBonus;
    if (adjusted > threshold) continue;
    if (!best || adjusted < best.dist) {
      best = { path: candidate, dist: adjusted };
    }
  }
  return best ? best.path : null;
}
