import fs from 'fs';
import path from 'path';

const ADMIN_ONLY_ROUTE_PREFIXES = [
  '/admin',
  '/admin-console',
  '/executive-dashboard',
  '/team-management',
  '/policy-console',
  '/admin-system',
  '/admin-activity-log',
  '/email-templates-admin',
  '/performance-observability',
  '/route-health-report',
  '/safe-deployment',
  '/ops-performance',
  '/ops-route-health',
  '/ai-feature-dashboard',
  '/i18n-drift-dashboard',
];

const isRouteInPrefix = (path: string, prefix: string) => path === prefix || path.startsWith(`${prefix}/`);
const isAdminOnlyRoute = (path: string) => ADMIN_ONLY_ROUTE_PREFIXES.some((prefix) => isRouteInPrefix(path, prefix));

describe('platform admin route visibility lock', () => {
  it('marks all top-level admin routes as admin-only', () => {
    const criticalRoutes = [
      '/admin-console',
      '/executive-dashboard',
      '/admin/system',
      '/admin/content-integrity',
      '/team-management',
      '/policy-console',
      '/ops-performance',
      '/ops-route-health',
      '/safe-deployment',
    ];

    criticalRoutes.forEach((route) => {
      expect(isAdminOnlyRoute(route)).toBe(true);
    });
  });

  it('does not mark regular user routes as admin-only', () => {
    const userRoutes = [
      '/dashboard',
      '/profile',
      '/settings',
      '/features/watch-videos',
      '/ai-learning-hub',
      '/auth/login',
    ];

    userRoutes.forEach((route) => {
      expect(isAdminOnlyRoute(route)).toBe(false);
    });
  });

  it('ensures high-risk admin tabs/pages stay admin-only', () => {
    const sensitiveAdminRoutes = [
      '/admin',
      '/admin/index',
      '/admin-console',
      '/executive-dashboard',
      '/team-management',
      '/policy-console',
      '/admin-system',
      '/admin-activity-log',
      '/email-templates-admin',
      '/performance-observability',
      '/route-health-report',
      '/safe-deployment',
      '/ops-performance',
      '/ops-route-health',
      '/ai-feature-dashboard',
      '/i18n-drift-dashboard',
    ];

    sensitiveAdminRoutes.forEach((route) => {
      expect(isAdminOnlyRoute(route)).toBe(true);
    });
  });

  it('requires shared AdminRouteGate on critical admin entry routes', () => {
    const read = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), relativePath), 'utf8');

    expect(read('app/(tabs)/admin-console.tsx')).toContain('AdminRouteGate');
    expect(read('app/admin-activity-log.tsx')).toContain('AdminRouteGate');
    expect(read('app/admin-system.tsx')).toContain('AdminRouteGate');
    expect(read('app/executive-dashboard.tsx')).toContain('AdminRouteGate');
    expect(read('app/admin/gdpr-requests.tsx')).toContain('AdminRouteGate');
    expect(read('app/admin/email-delivery-ledger.tsx')).toContain('AdminRouteGate');
    expect(read('app/talent-network-admin.tsx')).toContain('AdminRouteGate');
    expect(read('app/admin/_layout.tsx')).toContain('AdminRouteGate');
    expect(read('app/i18n-drift-dashboard.tsx')).toContain('AdminRouteGate');
    expect(read('app/ops-performance.tsx')).toContain('AdminRouteGate');
    expect(read('app/ops-route-health.tsx')).toContain('AdminRouteGate');
    expect(read('app/policy-console.tsx')).toContain('AdminRouteGate');
    expect(read('app/performance-observability.tsx')).toContain('AdminRouteGate');
    expect(read('app/route-health-report.tsx')).toContain('AdminRouteGate');
    expect(read('app/safe-deployment.tsx')).toContain('AdminRouteGate');
    expect(read('app/ai-feature-dashboard.tsx')).toContain('AdminRouteGate');
    expect(read('app/certificate-operations.tsx')).toContain('AdminRouteGate');
    expect(read('app/job-platform-admin.tsx')).toContain('AdminRouteGate');
    expect(read('app/team-management.tsx')).toContain('AdminRouteGate');
    expect(read('app/certificate-gallery.tsx')).toContain('AdminRouteGate');
  });

  it('uses shared admin identity helper instead of legacy role-array checks on mixed surfaces', () => {
    const read = (relativePath: string) => fs.readFileSync(path.join(process.cwd(), relativePath), 'utf8');

    expect(read('app/(tabs)/index.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/features/assistant.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/subscription/plans.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/subscription/mobile-money.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/job-platform-employer.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/job-platform.tsx')).toContain('hasAdminConsoleVisibility');
    expect(read('app/subscription/plans.tsx')).not.toContain("roles.includes('admin')");
  });
});
