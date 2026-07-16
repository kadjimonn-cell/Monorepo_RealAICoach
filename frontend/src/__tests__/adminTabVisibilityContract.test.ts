import { hasAdminConsoleVisibility } from '../utils/adminAccess';

describe('admin tab visibility contract (hide-only)', () => {
  it('hides admin tab for non-admin users', () => {
    expect(hasAdminConsoleVisibility(undefined)).toBe(false);
    expect(hasAdminConsoleVisibility(null)).toBe(false);
    expect(hasAdminConsoleVisibility({})).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: false })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 'false' })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 0 })).toBe(false);
  });

  it('shows admin tab only for true admin flag', () => {
    expect(hasAdminConsoleVisibility({ is_admin: true })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 'true' })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 1 })).toBe(true);
  });
});
