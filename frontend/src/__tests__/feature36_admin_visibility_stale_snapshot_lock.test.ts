import { canonicalizeAdminIdentity, hasAdminConsoleVisibility } from '../utils/adminAccess';

describe('Feature 36 admin visibility stale snapshot lock', () => {
  it('never grants admin visibility for non-admin payloads', () => {
    expect(hasAdminConsoleVisibility({ is_admin: false })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 0 })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 'false' })).toBe(false);
    expect(hasAdminConsoleVisibility({} as any)).toBe(false);
  });

  it('requires explicit positive admin signal only', () => {
    expect(hasAdminConsoleVisibility({ is_admin: true })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 1 })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 'true' })).toBe(true);
  });

  it('prevents role-only leakage from stale snapshots', () => {
    // stale local snapshots with role/roles/platform_role alone must not unlock admin console
    expect(hasAdminConsoleVisibility({ is_admin: undefined } as any)).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: null } as any)).toBe(false);
  });

  it('canonicalizeAdminIdentity removes role-based admin residue when is_admin is false', () => {
    const normalized = canonicalizeAdminIdentity({
      is_admin: false,
      role: 'admin',
      platform_role: 'admin',
      roles: ['user', 'admin', 'basic'],
    } as any) as any;

    expect(normalized.is_admin).toBe(false);
    expect(normalized.role).toBe('user');
    expect(normalized.platform_role).toBeNull();
    expect(normalized.roles).toEqual(['user', 'basic']);
  });

  it('canonicalizeAdminIdentity preserves admin role data when explicit is_admin is true', () => {
    const normalized = canonicalizeAdminIdentity({
      is_admin: true,
      role: 'admin',
      platform_role: 'admin',
      roles: ['admin', 'premium'],
    } as any) as any;

    expect(normalized.is_admin).toBe(true);
    expect(normalized.role).toBe('admin');
    expect(normalized.platform_role).toBe('admin');
    expect(normalized.roles).toEqual(['admin', 'premium']);
  });
});
