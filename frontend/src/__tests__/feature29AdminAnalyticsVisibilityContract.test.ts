import { hasAdminConsoleVisibility } from '../utils/adminAccess';

describe('Feature 29 admin analytics visibility contract', () => {
  it('hides admin analytics for non-admin users', () => {
    expect(hasAdminConsoleVisibility(undefined)).toBe(false);
    expect(hasAdminConsoleVisibility(null)).toBe(false);
    expect(hasAdminConsoleVisibility({})).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: false })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 'false' })).toBe(false);
    expect(hasAdminConsoleVisibility({ is_admin: 0 })).toBe(false);
  });

  it('shows admin analytics only for admin users', () => {
    expect(hasAdminConsoleVisibility({ is_admin: true })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 'true' })).toBe(true);
    expect(hasAdminConsoleVisibility({ is_admin: 1 })).toBe(true);
  });
});
