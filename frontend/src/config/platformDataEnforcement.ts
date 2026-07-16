export type ConsoleType = 'executive' | 'operations';
export type PlatformTabPhase = 'B';

const EXEC_PHASE_B = new Set([
  // Consolidated Phase-B hub tabs (P0 + P1 + P2)
  'exec-command-center',
  'exec-growth-experimentation-hub',
  'exec-ai-operations-hub',
  'exec-hiring-careers-hub',
  'exec-revenue-billing-hub',
  'exec-notifications-support-hub',
  'exec-security-trust-hub',
  'exec-identity-access-hub',
  'exec-observability-hub',
  'exec-integrations-content-hub',
  'exec-policy-compliance-hub',
  'exec-theme-globalization-hub',

  'llm-billing',
  'llm-usage-billing',
  'jobs',
  'iap-management',
  'iap',
  'id-checker',
  // Former Phase C/Phase A tabs promoted to Phase B
  'ai-features', 'ai-usage', 'content-studio-analytics', 'csat', 'global-adaptation', 'newsletter', 'newsletter-analytics',
  'onboarding-analytics', 'sso-analytics', 'ticket-feedback',
  'cdn-management', 'content', 'email-coverage', 'employer-portal', 'feedback-heatmap', 'integrations-mgmt',
  'keyword-tracking', 'leaderboard-mgmt', 'support-tickets', 'templates',
  'ai-support', 'automation-engine', 'notifications', 'otp', 'otp-delivery', 'performance', 'sessions', 'sla', 'webhooks',
  'ai-command-center', 'page-performance',
  'learning-hub-autopilot',
  'ab-testing', 'conversion', 'payment-billing', 'revenue', 'sub-analytics', 'subscription-mgmt', 'unified-revenue',
  'coaching-tips-cms', 'compliance-digests', 'device-audit', 'enterprise-security', 'fraud', 'gtec', 'pdf-policy',
  'security', 'siem', 'tickertape-analytics',
  'logs', 'platform-settings', 'system-monitor', 'theme-validation',

  // Existing Phase C
  'ai-analytics-link', 'users',
  'operations-console-link', 'performance-observability-link', 'policy-console-link', 'route-health-link',
  'overview',
  'financial', 'mm-analytics',
  'gdpr-requests', 'risk',
  'activity-log-link', 'system-dashboard-link',
]);

const OPS_PHASE_B = new Set([
  // Consolidated Phase-B hub tabs (P0 + P1 + P2)
  'ops-command-center',
  'growth-experimentation-hub',
  'ai-operations-hub',
  'hiring-careers-hub',
  'revenue-billing-hub',
  'notifications-messaging-hub',
  'support-ticketing-hub',
  'security-trust-hub',
  'identity-access-hub',
  'platform-health-observability-hub',
  'automation-reliability-hub',
  'integrations-webhooks-hub',
  'content-knowledge-hub',
  'policy-compliance-hub',
  'theme-brand-localization-hub',
  'mobile-distribution-hub',

  'iap',
  'llm-usage-billing',
  'career-applications',
  'talent-network-admin',
  // Former Phase C/Phase A tabs promoted to Phase B
  'ai-insights', 'ai-learning-hub-insights', 'ai-resolution', 'appstore-connect', 'auth-compliance-dashboard',
  'certificate-analytics', 'certificate-template-manager', 'executive-quality-dashboard', 'nova-analytics',
  'platform-analytics', 'seo-dashboard', 'team-analytics', 'uba-dashboard', 'unified-aso', 'web-vitals',
  'languages', 'receipt-branding', 'subscriber-growth', 'whitelabel',
  'ab-performance', 'accessibility', 'code-health',
  'ai-remediation', 'auto-detect', 'automation-engine', 'cookie-policy-broadcast', 'critical-journey-monitor',
  'legal-notice-broadcast', 'perf-advisor', 'performance-guardian', 'platform-integrations', 'platform-trust-center',
  'privacy-policy-broadcast', 'reality-validation', 'self-repair', 'system-health', 'theme-audit',
  'theme-governance-dashboard',
  'booking-center', 'hiring-analytics', 'user-insights',
  'access-matrix', 'google-verification', 'mfa-settings', 'security-incident-broadcast', 'security-posture',
  'security-recs', 'sso-status', 'threat-detection', 'zero-trust-root-cause-board',
  'payment-recovery',

  // Existing Phase C
  'anomaly-detection', 'campaign-dashboard', 'google-play', 'referral-analytics',
  'email-templates', 'newsletter-analytics',
  'ab-testing', 'batch-ai', 'webhook-replay',
  'provider-incidents',
  'payments-tax',
  'ai-platform-integrity', 'auto-scaling', 'autonomous-engine', 'changelog-mgmt', 'deployment-orchestration',
  'enterprise-control-plane', 'feature-manager', 'gps-state-management', 'notification-rules', 'ops-dashboard',
  'otp-delivery', 'platform-health', 'platform-settings', 'session-replay', 'theme-validation', 'tos-management',
  'ai-command-center', 'custom-dashboards', 'dashboard', 'live-activity',
  'reengagement', 'teams',
  'enterprise-security', 'security-incidents', 'waf-firewall', 'zero-trust-center',
  'churn-recovery', 'contact-submissions', 'escalation', 'faq-mgmt', 'helpdesk', 'notification-history',
  'ticket-assignment',
]);

export const getConsoleTabPhase = (consoleType: ConsoleType, tabId: string): PlatformTabPhase => {
  const id = String(tabId || '').trim();
  if (!id) return 'B';

  if (consoleType === 'executive') {
    if (EXEC_PHASE_B.has(id)) return 'B';
    return 'B';
  }

  if (OPS_PHASE_B.has(id)) return 'B';
  return 'B';
};

export const getRecommendedLiveTab = (consoleType: ConsoleType): string => {
  return consoleType === 'executive' ? 'jobs' : 'career-applications';
};
