import { getLandingRouteForRole } from '../lib/platformRoleLanding';

describe('platform role landing admin safety contract', () => {
  it('does not route non-admin platform roles to admin pages', () => {
    const roles = ['Manager', 'Developer', 'Engineer', 'Finance Advisor'];
    const forbiddenPrefixes = ['/admin', '/team-management', '/policy-console', '/admin-system', '/executive-dashboard'];

    roles.forEach((role) => {
      const route = getLandingRouteForRole(role);
      forbiddenPrefixes.forEach((prefix) => {
        expect(route.startsWith(prefix)).toBe(false);
      });
    });
  });

  it('keeps support team role on non-admin queue', () => {
    expect(getLandingRouteForRole('Support Team')).toBe('/my-tickets');
  });
});
