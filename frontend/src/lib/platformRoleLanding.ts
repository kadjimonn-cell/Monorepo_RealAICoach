/**
 * Role-specific landing route mapping.
 *
 * Different platform employees should land on a role-tailored page after
 * signing in or completing invitation acceptance — instead of a generic
 * `/home` that's mostly gated behind upgrade prompts.
 *
 * Kept deliberately tiny: one function, string→string mapping, no side effects.
 * Used by `invite-accept.tsx` (post-accept redirect) and `LoginInner.tsx`
 * (post-login redirect for platform employees).
 */

export type PlatformRole =
  | 'Manager'
  | 'Support Team'
  | 'Developer'
  | 'Engineer'
  | 'Finance Advisor'
  | 'Designer'
  | 'QA'
  | 'Marketing'
  | 'Operations'
  | 'Custom'
  | string;

const ROLE_TO_LANDING: Record<string, string> = {
  // Customer-facing teams — go straight to their queue
  'Support Team': '/my-tickets',

  // Non-admin platform roles must never auto-land on admin pages.
  // Keep role-tailored but non-admin-safe destinations.
  'Developer': '/dashboard',
  'Engineer': '/dashboard',
  'Finance Advisor': '/my-analytics',
  'Manager': '/dashboard',

  // Growth / GTM — analytics first
  'Marketing': '/my-analytics',
  'Operations': '/my-analytics',
};

/**
 * Given a platform role (or null/undefined for regular users), returns the
 * route path the user should land on after a successful auth event.
 *
 * Falls back to `/home` for:
 *   - unknown/custom roles
 *   - users without a `platform_role` (regular subscribers / free users)
 *   - the "Custom" role (intentionally undirected)
 */
export function getLandingRouteForRole(platformRole?: string | null): string {
  if (!platformRole) return '/home';
  return ROLE_TO_LANDING[platformRole] || '/home';
}
