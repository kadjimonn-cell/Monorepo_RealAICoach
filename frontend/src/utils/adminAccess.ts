type UserLike = {
  is_admin?: boolean | string | number | null;
  role?: string | null;
  platform_role?: string | null;
  roles?: any[];
};

export const hasAdminConsoleVisibility = (user?: UserLike | null): boolean => {
  if (!user) return false;
  const raw = user.is_admin;
  if (raw === true) return true;
  if (raw === 1) return true;
  if (typeof raw === 'string') return raw.trim().toLowerCase() === 'true';
  return false;
};

export const canonicalizeAdminIdentity = <T extends Record<string, any>>(user?: T | null): T | null => {
  if (!user || typeof user !== 'object') return null;
  const next: Record<string, any> = { ...user };
  const isAdmin = hasAdminConsoleVisibility(next as any);
  next.is_admin = isAdmin;

  // Platform-locked rule: ONLY explicit is_admin grants admin surfaces.
  // Prevent role/roles/platform_role residue from elevating non-admin UI.
  if (!isAdmin) {
    const role = String(next.role || '').toLowerCase();
    if (role === 'admin') next.role = 'user';

    const platformRole = String(next.platform_role || '').toLowerCase();
    if (platformRole === 'admin') next.platform_role = null;

    if (Array.isArray(next.roles)) {
      next.roles = next.roles.filter((r: any) => String(r || '').toLowerCase() !== 'admin');
    }
  }

  return next as T;
};
