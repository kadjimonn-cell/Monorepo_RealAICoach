export type MergePhase = 'P0' | 'P1' | 'P2';

export interface MergeLegacyTab {
  id: string;
  label: string;
  icon: string;
  route?: string;
}

export interface MergeHubDefinition {
  id: string;
  label: string;
  icon: string;
  phase: MergePhase;
  description: string;
  legacyTabs: MergeLegacyTab[];
}

const buildLegacyToHubMap = (hubs: MergeHubDefinition[]) => {
  return hubs.reduce((acc, hub) => {
    acc[hub.id] = hub.id;
    hub.legacyTabs.forEach((tab) => {
      acc[tab.id] = hub.id;
    });
    return acc;
  }, {} as Record<string, string>);
};

// Batch-1 canonicalization aliases retained for backward compatibility.
export const EXECUTIVE_BATCH1_SECTION_ALIASES: Record<string, string> = {
  'iap-management': 'iap',
  'llm-billing': 'llm-usage-billing',
  newsletter: 'newsletter-analytics',
  otp: 'otp-delivery',
  'ai-features': 'ai-analytics-link',
  'ai-usage': 'ai-analytics-link',
};

export const OPERATIONS_PHASE_B_HUBS: MergeHubDefinition[] = [
  {
    id: 'ops-command-center',
    label: 'Command Center',
    icon: 'grid',
    phase: 'P0',
    description: 'Unified command dashboard for global operations runtime and executive quality visibility.',
    legacyTabs: [
      { id: 'dashboard', label: 'Control Dashboard', icon: 'grid' },
      { id: 'ops-dashboard', label: 'Operations Center', icon: 'earth' },
      { id: 'live-activity', label: 'Live Activity Feed', icon: 'pulse' },
      { id: 'custom-dashboards', label: 'Customize Layout', icon: 'options' },
      { id: 'platform-settings', label: 'Platform Settings', icon: 'settings' },
      { id: 'executive-quality-dashboard', label: 'Executive Quality Dashboard', icon: 'shield-half' },
    ],
  },
  {
    id: 'growth-experimentation-hub',
    label: 'Growth & Experimentation',
    icon: 'flask',
    phase: 'P1',
    description: 'Single workspace for A/B testing, campaign analytics, SEO/ASO, and funnel conversion monitoring.',
    legacyTabs: [
      { id: 'ab-testing', label: 'Email A/B Tests', icon: 'flask' },
      { id: 'ab-performance', label: 'A/B Performance', icon: 'stats-chart' },
      { id: 'campaign-dashboard', label: 'Campaigns', icon: 'rocket' },
      { id: 'critical-journey-monitor', label: 'Critical Journey Monitor', icon: 'pulse' },
      { id: 'seo-dashboard', label: 'SEO & ASO', icon: 'search' },
      { id: 'subscriber-growth', label: 'Subscriber Growth', icon: 'trending-up' },
      { id: 'reengagement', label: 'Re-engagement', icon: 'arrow-undo-circle' },
      { id: 'referral-analytics', label: 'Referral Program', icon: 'gift' },
      { id: 'nova-analytics', label: 'Nova AI Analytics', icon: 'sparkles' },
      { id: 'platform-analytics', label: 'Platform Analytics', icon: 'pulse' },
      { id: 'web-vitals', label: 'Web Vitals', icon: 'speedometer' },
    ],
  },
  {
    id: 'ai-operations-hub',
    label: 'AI Operations',
    icon: 'sparkles',
    phase: 'P1',
    description: 'Consolidated AI command, quality, integrity, remediation, and learning intelligence operations.',
    legacyTabs: [
      { id: 'ai-command-center', label: 'AI Command Center', icon: 'sparkles' },
      { id: 'ai-insights', label: 'AI Insights', icon: 'bulb' },
      { id: 'ai-learning-hub-insights', label: 'AI Learning Hub Insights', icon: 'school' },
      { id: 'ai-platform-integrity', label: 'AI Platform Integrity', icon: 'shield-checkmark' },
      { id: 'ai-remediation', label: 'AI Remediation', icon: 'medkit' },
      { id: 'ai-resolution', label: 'AI Resolution', icon: 'sparkles' },
      { id: 'batch-ai', label: 'Batch AI', icon: 'color-wand' },
      { id: 'auto-detect', label: 'AI Auto-Detection', icon: 'shield-checkmark' },
    ],
  },
  {
    id: 'hiring-careers-hub',
    label: 'Hiring & Careers',
    icon: 'briefcase',
    phase: 'P1',
    description: 'End-to-end careers flow: applications, hiring analytics, scheduling, and candidate intelligence.',
    legacyTabs: [
      { id: 'career-applications', label: 'Career Applications', icon: 'document-text' },
      { id: 'talent-network-admin', label: 'Talent Network', icon: 'people' },
      { id: 'hiring-analytics', label: 'Hiring Analytics', icon: 'stats-chart' },
      { id: 'booking-center', label: 'Booking Center', icon: 'calendar' },
      { id: 'user-insights', label: 'User Insights', icon: 'eye' },
    ],
  },
  {
    id: 'revenue-billing-hub',
    label: 'Revenue & Billing',
    icon: 'cash',
    phase: 'P1',
    description: 'Unified billing, tax, payment recovery, IAP, receipts, and LLM usage monetization control.',
    legacyTabs: [
      { id: 'llm-usage-billing', label: 'LLM Usage & Billing', icon: 'receipt' },
      { id: 'payments-tax', label: 'Payments & Tax', icon: 'card' },
      { id: 'payment-recovery', label: 'Payment Recovery', icon: 'card' },
      { id: 'iap', label: 'In-App Purchases', icon: 'phone-portrait' },
      { id: 'receipt-branding', label: 'Receipt Branding', icon: 'receipt' },
    ],
  },
  {
    id: 'notifications-messaging-hub',
    label: 'Notifications & Messaging',
    icon: 'notifications',
    phase: 'P1',
    description: 'All outbound/inbound messaging controls, templates, history, and delivery policy.',
    legacyTabs: [
      { id: 'notification-history', label: 'Notification History', icon: 'notifications' },
      { id: 'notification-rules', label: 'Notification Rules', icon: 'notifications' },
      { id: 'email-guardrail-control-center', label: 'Email Guardrail Control Center', icon: 'shield-checkmark' },
      { id: 'email-templates', label: 'Email Templates', icon: 'mail' },
      { id: 'email-reliability', label: 'Email Reliability', icon: 'pulse' },
      { id: 'newsletter-analytics', label: 'Newsletter Analytics', icon: 'analytics' },
      { id: 'contact-submissions', label: 'Contact Submissions', icon: 'mail' },
    ],
  },
  {
    id: 'support-ticketing-hub',
    label: 'Support & Ticketing',
    icon: 'chatbubbles',
    phase: 'P1',
    description: 'Centralized support operations for assignment, escalations, FAQs, and churn interventions.',
    legacyTabs: [
      { id: 'helpdesk', label: 'Help Desk', icon: 'chatbubbles' },
      { id: 'ticket-assignment', label: 'Ticket Assignment', icon: 'git-branch' },
      { id: 'escalation', label: 'Escalation', icon: 'alert-circle' },
      { id: 'faq-mgmt', label: 'FAQ Manager', icon: 'help-circle' },
      { id: 'churn-recovery', label: 'Churn Recovery', icon: 'heart-dislike' },
    ],
  },
  {
    id: 'security-trust-hub',
    label: 'Security & Trust',
    icon: 'shield-checkmark',
    phase: 'P1',
    description: 'Consolidated trust posture, incident response, and zero-trust enforcement stack.',
    legacyTabs: [
      { id: 'enterprise-security', label: 'Enterprise Security', icon: 'shield-checkmark' },
      { id: 'security-posture', label: 'Security Posture', icon: 'shield-checkmark' },
      { id: 'security-incidents', label: 'Security Incidents', icon: 'alert-circle' },
      { id: 'security-recs', label: 'AI Recommendations', icon: 'sparkles' },
      { id: 'threat-detection', label: 'Threat Detection', icon: 'eye' },
      { id: 'waf-firewall', label: 'WAF & Firewall', icon: 'flame' },
      { id: 'zero-trust-center', label: 'Zero-Trust Center', icon: 'shield-checkmark' },
      { id: 'zero-trust-root-cause-board', label: 'Zero-Trust Root-Cause Board', icon: 'analytics' },
      { id: 'platform-trust-center', label: 'Platform Trust Center', icon: 'shield-checkmark' },
      { id: 'security-incident-broadcast', label: 'Incident Broadcast', icon: 'warning' },
      { id: 'anomaly-detection', label: 'Anomaly Detection', icon: 'warning' },
      { id: 'auth-compliance-dashboard', label: 'Auth Compliance', icon: 'shield-checkmark' },
      { id: 'uba-dashboard', label: 'User Behavior Analytics', icon: 'people-circle' },
      { id: 'reality-validation', label: 'Reality Validation', icon: 'checkmark-done-circle' },
      { id: 'gps-state-management', label: 'GPS State Management', icon: 'layers' },
    ],
  },
  {
    id: 'identity-access-hub',
    label: 'Identity & Access',
    icon: 'key',
    phase: 'P1',
    description: 'IAM governance for access matrix, SSO, MFA, OTP, sessions, and team controls.',
    legacyTabs: [
      { id: 'access-matrix', label: 'Access Matrix', icon: 'grid' },
      { id: 'mfa-settings', label: 'MFA Management', icon: 'key' },
      { id: 'sso-status', label: 'SSO Providers', icon: 'log-in' },
      { id: 'google-verification', label: 'Google Verification', icon: 'logo-google' },
      { id: 'otp-delivery', label: 'OTP Delivery', icon: 'keypad' },
      { id: 'session-replay', label: 'Session Replay', icon: 'videocam' },
      { id: 'teams', label: 'Teams', icon: 'people-circle' },
    ],
  },
  {
    id: 'platform-health-observability-hub',
    label: 'Platform Health & Observability',
    icon: 'pulse',
    phase: 'P1',
    description: 'Unified reliability, quality, telemetry, and runtime observability command surface.',
    legacyTabs: [
      { id: 'platform-health', label: 'Platform Health', icon: 'medical' },
      { id: 'assigned-host', label: 'Assigned Host', icon: 'git-network' },
      { id: 'system-health', label: 'System Health', icon: 'pulse' },
      { id: 'performance-guardian', label: 'Performance Guardian', icon: 'shield-checkmark' },
      { id: 'perf-advisor', label: 'Performance Advisor', icon: 'speedometer' },
      { id: 'code-health', label: 'Code Health', icon: 'checkmark-circle' },
      { id: 'entitlement-drift-audit', label: 'Entitlement Drift Audit', icon: 'git-compare' },
      { id: 'autonomous-engine', label: 'Autonomous Engine', icon: 'rocket' },
    ],
  },
  {
    id: 'automation-reliability-hub',
    label: 'Automation & Reliability',
    icon: 'construct',
    phase: 'P2',
    description: 'Automation orchestration, deployment controls, self-healing, and scaling operations.',
    legacyTabs: [
      { id: 'automation-engine', label: 'Automation Engine', icon: 'flash' },
      { id: 'enterprise-control-plane', label: 'Enterprise Control Plane', icon: 'git-network' },
      { id: 'feature-manager', label: 'Feature Manager', icon: 'apps' },
      { id: 'deployment-orchestration', label: 'Deployments', icon: 'rocket' },
      { id: 'auto-scaling', label: 'Auto-Scaling', icon: 'speedometer' },
      { id: 'self-repair', label: 'Self-Repair Engine', icon: 'construct' },
    ],
  },
  {
    id: 'integrations-webhooks-hub',
    label: 'Integrations & Webhooks',
    icon: 'git-network',
    phase: 'P1',
    description: 'Integration setup, replay diagnostics, and platform service connectivity governance.',
    legacyTabs: [
      { id: 'platform-integrations', label: 'Platform Integrations', icon: 'git-network' },
      { id: 'webhook-replay', label: 'Replay Center', icon: 'refresh-circle' },
    ],
  },
  {
    id: 'content-knowledge-hub',
    label: 'Content & Knowledge',
    icon: 'document-text',
    phase: 'P2',
    description: 'Knowledge, documentation, certificates, language quality, and brand surfaces in one place.',
    legacyTabs: [
      { id: 'changelog-mgmt', label: 'Changelog / What\'s New', icon: 'newspaper' },
      { id: 'certificate-analytics', label: 'Certificate Analytics', icon: 'ribbon' },
      { id: 'certificate-template-manager', label: 'Certificate Template', icon: 'construct' },
      { id: 'languages', label: 'Languages', icon: 'language' },
      { id: 'whitelabel', label: 'White-Label', icon: 'color-fill' },
      { id: 'accessibility', label: 'Accessibility', icon: 'eye' },
    ],
  },
  {
    id: 'policy-compliance-hub',
    label: 'Policy & Compliance',
    icon: 'document-text',
    phase: 'P2',
    description: 'Policy lifecycle, legal broadcasts, and compliance communication governance.',
    legacyTabs: [
      { id: 'tos-management', label: 'Terms of Service', icon: 'document-text' },
      { id: 'legal-notice-broadcast', label: 'Legal Notice Broadcast', icon: 'megaphone' },
      { id: 'privacy-policy-broadcast', label: 'Privacy Policy Updated', icon: 'lock-closed' },
      { id: 'cookie-policy-broadcast', label: 'Cookie Policy Updated', icon: 'nutrition' },
    ],
  },
  {
    id: 'theme-brand-localization-hub',
    label: 'Theme, Brand & Localization',
    icon: 'color-palette',
    phase: 'P2',
    description: 'Theme v2 compliance, governance controls, and cross-brand localization quality operations.',
    legacyTabs: [
      { id: 'theme-validation', label: 'Theme Validation', icon: 'color-palette' },
      { id: 'theme-governance-dashboard', label: 'Theme Governance Dashboard', icon: 'shield-checkmark' },
      { id: 'theme-audit', label: 'Theme Audit', icon: 'shield-checkmark' },
    ],
  },
  {
    id: 'mobile-distribution-hub',
    label: 'Mobile Distribution',
    icon: 'phone-portrait',
    phase: 'P2',
    description: 'App-store delivery and ASO distribution governance for mobile channel quality.',
    legacyTabs: [
      { id: 'appstore-connect', label: 'App Store Connect', icon: 'logo-apple' },
      { id: 'google-play', label: 'Google Play Console', icon: 'logo-google-playstore' },
      { id: 'unified-aso', label: 'Unified ASO Reports', icon: 'analytics' },
    ],
  },
];

export const EXECUTIVE_PHASE_B_HUBS: MergeHubDefinition[] = [
  {
    id: 'exec-command-center',
    label: 'Command Center',
    icon: 'grid',
    phase: 'P0',
    description: 'Unified executive command entry for oversight, links, and global system snapshots.',
    legacyTabs: [
      { id: 'overview', label: 'Executive Overview', icon: 'grid' },
      { id: 'operations-console-link', label: 'Operations Console', icon: 'construct', route: '/admin-console?category=overview&tab=ops-command-center' },
      { id: 'system-dashboard-link', label: 'System Dashboard', icon: 'server', route: '/admin-system' },
      { id: 'activity-log-link', label: 'Activity Log', icon: 'list', route: '/admin-activity-log' },
      { id: 'page-performance', label: 'Page Load Monitor', icon: 'timer' },
    ],
  },
  {
    id: 'exec-growth-experimentation-hub',
    label: 'Growth & Experimentation',
    icon: 'flask',
    phase: 'P1',
    description: 'Revenue-side experimentation and growth conversion tracking in one executive surface.',
    legacyTabs: [
      { id: 'conversion', label: 'Conversion Analytics', icon: 'funnel' },
      { id: 'ab-testing', label: 'A/B Testing', icon: 'flask' },
      { id: 'onboarding-analytics', label: 'Onboarding Analytics', icon: 'rocket' },
      { id: 'keyword-tracking', label: 'Keyword Tracking', icon: 'search' },
      { id: 'tickertape-analytics', label: 'Welcome · Tickertape CTR', icon: 'analytics' },
      { id: 'mm-analytics', label: 'Mobile Money Analytics', icon: 'phone-portrait', route: '/admin/mobile-money-dashboard' },
    ],
  },
  {
    id: 'exec-ai-operations-hub',
    label: 'AI Operations',
    icon: 'sparkles',
    phase: 'P1',
    description: 'AI usage, features, adaptation, and content intelligence controls for leadership.',
    legacyTabs: [
      { id: 'ai-command-center', label: 'AI Command Center', icon: 'sparkles' },
      { id: 'learning-hub-autopilot', label: 'Learning Hub Autopilot', icon: 'school' },
      { id: 'ai-support', label: 'AI Auto-Support', icon: 'chatbubbles' },
      { id: 'content-studio-analytics', label: 'Content Studio', icon: 'create' },
      { id: 'ai-analytics-link', label: 'AI Analytics', icon: 'bar-chart', route: '/ai-feature-dashboard' },
      { id: 'global-adaptation', label: 'Global Adaptation Center', icon: 'globe' },
    ],
  },
  {
    id: 'exec-hiring-careers-hub',
    label: 'Hiring & Careers',
    icon: 'briefcase',
    phase: 'P1',
    description: 'Job operations, employer portal visibility, and identity checks for hiring governance.',
    legacyTabs: [
      { id: 'jobs', label: 'Job Control Center', icon: 'briefcase' },
      { id: 'employer-portal', label: 'Jobs Portal', icon: 'business' },
      { id: 'id-checker', label: 'ID Checker', icon: 'shield-checkmark' },
      { id: 'leaderboard-mgmt', label: 'Leaderboard Mgmt', icon: 'trophy' },
    ],
  },
  {
    id: 'exec-revenue-billing-hub',
    label: 'Revenue & Billing',
    icon: 'cash',
    phase: 'P1',
    description: 'Consolidated financial intelligence, subscriptions, and monetization controls.',
    legacyTabs: [
      { id: 'financial', label: 'Financial Intelligence', icon: 'bar-chart' },
      { id: 'unified-revenue', label: 'Unified Revenue', icon: 'wallet' },
      { id: 'revenue', label: 'Revenue Analytics', icon: 'trending-up' },
      { id: 'sub-analytics', label: 'Subscription Analytics', icon: 'card' },
      { id: 'payment-billing', label: 'Payment & Billing', icon: 'cash' },
      { id: 'subscription-mgmt', label: 'Subscription Plans', icon: 'pricetags' },
      { id: 'iap', label: 'In-App Purchases', icon: 'phone-portrait' },
      { id: 'llm-usage-billing', label: 'LLM Usage & Billing', icon: 'cash' },
    ],
  },
  {
    id: 'exec-notifications-support-hub',
    label: 'Notifications & Support',
    icon: 'notifications',
    phase: 'P1',
    description: 'Executive visibility into support, ticket quality, communication, and notification governance.',
    legacyTabs: [
      { id: 'notifications', label: 'Notification Mgmt', icon: 'notifications' },
      { id: 'support-tickets', label: 'Support & Tickets', icon: 'headset' },
      { id: 'csat', label: 'CSAT Dashboard', icon: 'happy' },
      { id: 'ticket-feedback', label: 'Ticket Feedback Intel', icon: 'chatbox-ellipses' },
      { id: 'newsletter-analytics', label: 'Newsletter Analytics', icon: 'newspaper' },
      { id: 'email-coverage', label: 'Email Coverage Matrix', icon: 'mail' },
      { id: 'feedback-heatmap', label: 'Friction Heatmap', icon: 'flame' },
      { id: 'templates', label: 'Email Gallery', icon: 'images' },
    ],
  },
  {
    id: 'exec-security-trust-hub',
    label: 'Security & Trust',
    icon: 'shield-half',
    phase: 'P1',
    description: 'Security posture, fraud, SIEM, compliance, and trust governance in one leadership lens.',
    legacyTabs: [
      { id: 'security', label: 'Security Dashboard', icon: 'lock-closed' },
      { id: 'enterprise-security', label: 'Enterprise Security', icon: 'shield-half' },
      { id: 'fraud', label: 'Fraud Detection', icon: 'warning' },
      { id: 'siem', label: 'SIEM', icon: 'shield' },
      { id: 'risk', label: 'Risk & Compliance', icon: 'shield-checkmark' },
      { id: 'gdpr-requests', label: 'GDPR Self-Service', icon: 'shield-checkmark-outline', route: '/admin/gdpr-requests' },
      { id: 'pdf-policy', label: 'PDF Policy Monitor', icon: 'document-text' },
      { id: 'compliance-digests', label: 'Compliance Digest Hub', icon: 'mail-unread' },
      { id: 'gtec', label: 'GTEC C5 (Autonomous)', icon: 'analytics' },
      { id: 'device-audit', label: 'Device Audit', icon: 'hardware-chip' },
    ],
  },
  {
    id: 'exec-identity-access-hub',
    label: 'Identity & Access',
    icon: 'key',
    phase: 'P1',
    description: 'Identity governance including users, sessions, SSO, OTP, and SLA-linked access readiness.',
    legacyTabs: [
      { id: 'users', label: 'User Management', icon: 'people-circle' },
      { id: 'sessions', label: 'Session Management', icon: 'key' },
      { id: 'sso-analytics', label: 'SSO Analytics', icon: 'finger-print' },
      { id: 'otp-delivery', label: 'OTP Delivery', icon: 'keypad' },
      { id: 'sla', label: 'SLA Monitor', icon: 'timer' },
    ],
  },
  {
    id: 'exec-observability-hub',
    label: 'Observability & Reliability',
    icon: 'pulse',
    phase: 'P1',
    description: 'Performance, logs, runtime monitor, route health, and platform observability for leadership.',
    legacyTabs: [
      { id: 'performance', label: 'Performance', icon: 'speedometer' },
      { id: 'performance-observability-link', label: 'Performance Observability', icon: 'speedometer', route: '/ops-performance' },
      { id: 'route-health-link', label: 'Route Health', icon: 'pulse', route: '/ops-route-health' },
      { id: 'logs', label: 'Logs & Audit', icon: 'list' },
      { id: 'system-monitor', label: 'System Monitor', icon: 'pulse' },
      { id: 'cdn-management', label: 'CDN Management', icon: 'globe' },
      { id: 'webhooks', label: 'Webhook Events', icon: 'git-branch' },
    ],
  },
  {
    id: 'exec-platform-settings-hub',
    label: 'Platform Settings',
    icon: 'settings',
    phase: 'P1',
    description: 'Global platform operations center for live status, maintenance, configuration, and incident controls.',
    legacyTabs: [
      { id: 'platform-settings', label: 'Platform Settings', icon: 'settings' },
    ],
  },
  {
    id: 'exec-email-guardrail-hub',
    label: 'Email Guardrail',
    icon: 'shield-checkmark',
    phase: 'P1',
    description: 'Control center for cap-block events, unblock review workflow, and template-wise email cap governance.',
    legacyTabs: [
      { id: 'email-guardrail-control-center', label: 'Email Guardrail Control Center', icon: 'shield-checkmark' },
    ],
  },
  {
    id: 'exec-integrations-content-hub',
    label: 'Integrations & Content',
    icon: 'git-network',
    phase: 'P2',
    description: 'Consolidated integrations and content governance surfaces for commercial operations.',
    legacyTabs: [
      { id: 'integrations-mgmt', label: 'Integration Mgmt', icon: 'git-network' },
      { id: 'content', label: 'Content Management', icon: 'document-text' },
      { id: 'coaching-tips-cms', label: 'Welcome · Tip Catalog', icon: 'bulb' },
    ],
  },
  {
    id: 'exec-policy-compliance-hub',
    label: 'Policy & Compliance',
    icon: 'shield',
    phase: 'P2',
    description: 'Policy-console access and compliance execution surfaces for global leadership controls.',
    legacyTabs: [
      { id: 'policy-console-link', label: 'Policy Console', icon: 'shield', route: '/policy-console' },
    ],
  },
  {
    id: 'exec-legal-update-hub',
    label: 'LEGAL UPDATE',
    icon: 'document-text',
    phase: 'P1',
    description: 'Global legal governance center for Cookies, Privacy Policy, and Terms operations.',
    legacyTabs: [
      { id: 'legal-update', label: 'LEGAL UPDATE', icon: 'document-text' },
    ],
  },
  {
    id: 'exec-theme-globalization-hub',
    label: 'Theme & Globalization',
    icon: 'color-palette',
    phase: 'P2',
    description: 'Global UI theme validation and regional adaptation quality control.',
    legacyTabs: [
      { id: 'theme-validation', label: 'Theme Validation', icon: 'color-palette' },
    ],
  },
];

export const OPERATIONS_LEGACY_TAB_TO_HUB = buildLegacyToHubMap(OPERATIONS_PHASE_B_HUBS);
export const EXECUTIVE_LEGACY_TAB_TO_HUB = buildLegacyToHubMap(EXECUTIVE_PHASE_B_HUBS);

export const getOperationsHubById = (tabId: string) => {
  return OPERATIONS_PHASE_B_HUBS.find((hub) => hub.id === tabId) || null;
};

export const getExecutiveHubById = (tabId: string) => {
  return EXECUTIVE_PHASE_B_HUBS.find((hub) => hub.id === tabId) || null;
};
