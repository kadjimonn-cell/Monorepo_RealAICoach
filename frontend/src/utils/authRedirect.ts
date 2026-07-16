import { normalizeIncomingSystemPath } from './routeResolution';

export function buildWelcomeAuthRedirect(path: string, reason = 'unauthenticated'): string {
  const encodedReturnTo = encodeURIComponent(normalizeIncomingSystemPath(path || '/dashboard'));
  const normalizedReason = String(reason || 'unauthenticated').trim() || 'unauthenticated';
  const encodedReason = encodeURIComponent(normalizedReason);
  return `/welcome?return_to=${encodedReturnTo}&auth_reason=${encodedReason}`;
}