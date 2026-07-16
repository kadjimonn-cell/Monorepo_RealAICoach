export type SharedCapabilityId =
  | 'ai-command-center'
  | 'automation-engine'
  | 'platform-settings'
  | 'theme-validation'
  | 'enterprise-security'
  | 'otp-delivery'
  | 'newsletter-analytics'
  | 'email-templates'
  | 'in-app-purchases';

export interface SharedConsoleTabContract {
  tabId: string;
  label: string;
  icon: string;
  route: string;
  categoryId: string;
  i18nKey: string | null;
  permissionGate: 'admin-only' | 'admin-or-operations-manager';
  featureFlags: string[];
}

export interface SharedCapabilityContract {
  capabilityId: SharedCapabilityId;
  businessPurpose: string;
  sharedComponent: string;
  executive: SharedConsoleTabContract;
  operations: SharedConsoleTabContract;
}

/**
 * Debug-only module versions for console navigation surfaces.
 * These badges are intentionally hidden in standard mode and shown only when
 * each console enables Debug / Advanced mode.
 */
export const CONSOLE_TAB_DEBUG_VERSIONS: Record<string, string> = {
  'ai-command-center': '7.3.1',
  dashboard: '7.2.4',
  overview: '7.2.0',
  'live-activity': '7.1.9',
  'enterprise-control-plane': '7.3.1',
  'platform-settings': '7.2.8',
  'automation-engine': '7.2.6',
  'theme-validation': '7.2.5',
  'executive-quality-dashboard': '7.1.8',
  'critical-journey-monitor': '7.2.2',
  'performance-guardian': '7.1.7',
  'platform-health': '7.2.1',
  'security-incidents': '7.1.5',
  'payment-billing': '7.0.9',
  'payments-tax': '7.1.3',
  iap: '7.0.7',
  'iap-management': '7.0.7',
  'llm-usage-billing': '7.1.4',
  'llm-billing': '7.1.4',
  otp: '7.1.6',
  'otp-delivery': '7.1.6',
  'learning-hub-autopilot': '7.4.0',
  newsletter: '7.1.2',
  'newsletter-analytics': '7.1.2',
};

export const SHARED_CONSOLE_CAPABILITIES: SharedCapabilityContract[] = [
  {
    capabilityId: 'ai-command-center',
    businessPurpose: 'Centralized AI operations and controls',
    sharedComponent: 'AICommandCenterPanel',
    executive: {
      tabId: 'ai-command-center',
      label: 'AI Command Center',
      icon: 'sparkles',
      route: '/executive-dashboard?section=ai-command-center',
      categoryId: 'overview',
      i18nKey: 'executive.section.ai-command-center',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'ai-command-center',
      label: 'AI Command Center',
      icon: 'sparkles',
      route: '/admin-console?category=overview&tab=ai-command-center',
      categoryId: 'overview',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'automation-engine',
    businessPurpose: 'Automation orchestration and execution controls',
    sharedComponent: 'AutomationEnginePanel',
    executive: {
      tabId: 'automation-engine',
      label: 'Automation Engine',
      icon: 'cog',
      route: '/executive-dashboard?section=automation-engine',
      categoryId: 'operations',
      i18nKey: 'executive.section.automation-engine',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'automation-engine',
      label: 'Automation Engine',
      icon: 'flash',
      route: '/admin-console?category=operations&tab=automation-engine',
      categoryId: 'operations',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'platform-settings',
    businessPurpose: 'Global platform-level configuration governance',
    sharedComponent: 'PlatformSettingsPanel',
    executive: {
      tabId: 'platform-settings',
      label: 'Platform Settings',
      icon: 'settings',
      route: '/executive-dashboard?section=platform-settings',
      categoryId: 'system',
      i18nKey: 'executive.section.platform-settings',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'platform-settings',
      label: 'Platform Settings',
      icon: 'settings',
      route: '/admin-console?category=operations&tab=platform-settings',
      categoryId: 'operations',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'theme-validation',
    businessPurpose: 'Theme v2 compliance scanning and validation',
    sharedComponent: 'ThemeValidationDashboard',
    executive: {
      tabId: 'theme-validation',
      label: 'Theme Validation',
      icon: 'color-palette',
      route: '/executive-dashboard?section=theme-validation',
      categoryId: 'system',
      i18nKey: 'executive.section.theme-validation',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'theme-validation',
      label: 'Theme Validation',
      icon: 'color-palette',
      route: '/admin-console?category=operations&tab=theme-validation',
      categoryId: 'operations',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'enterprise-security',
    businessPurpose: 'Enterprise security controls and compliance posture',
    sharedComponent: 'EnterpriseSecurityPanel',
    executive: {
      tabId: 'enterprise-security',
      label: 'Enterprise Security',
      icon: 'shield-half',
      route: '/executive-dashboard?section=enterprise-security',
      categoryId: 'security',
      i18nKey: 'executive.section.enterprise-security',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'enterprise-security',
      label: 'Enterprise Security',
      icon: 'shield-checkmark',
      route: '/admin-console?category=security&tab=enterprise-security',
      categoryId: 'security',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'otp-delivery',
    businessPurpose: 'OTP pipeline performance and delivery integrity',
    sharedComponent: 'OTPDeliveryDashboardPanel',
    executive: {
      tabId: 'otp-delivery',
      label: 'OTP Delivery',
      icon: 'keypad',
      route: '/executive-dashboard?section=otp-delivery',
      categoryId: 'operations',
      i18nKey: 'executive.section.otp',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'otp-delivery',
      label: 'OTP Delivery',
      icon: 'keypad',
      route: '/admin-console?category=operations&tab=otp-delivery',
      categoryId: 'operations',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'newsletter-analytics',
    businessPurpose: 'Newsletter engagement and delivery analytics',
    sharedComponent: 'NewsletterAnalyticsPanel',
    executive: {
      tabId: 'newsletter-analytics',
      label: 'Newsletter Analytics',
      icon: 'newspaper',
      route: '/executive-dashboard?section=newsletter-analytics',
      categoryId: 'intelligence',
      i18nKey: 'executive.section.newsletter',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'newsletter-analytics',
      label: 'Newsletter Analytics',
      icon: 'analytics',
      route: '/admin-console?category=comms&tab=newsletter-analytics',
      categoryId: 'comms',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'email-templates',
    businessPurpose: 'Email template management and rendering governance',
    sharedComponent: 'EmailTemplatesPanel',
    executive: {
      tabId: 'templates',
      label: 'Email Gallery',
      icon: 'images',
      route: '/executive-dashboard?section=templates',
      categoryId: 'management',
      i18nKey: 'executive.section.templates',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'email-templates',
      label: 'Email Templates',
      icon: 'color-palette',
      route: '/admin-console?category=comms&tab=email-templates',
      categoryId: 'comms',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
  {
    capabilityId: 'in-app-purchases',
    businessPurpose: 'In-app purchase operations and subscription reconciliation',
    sharedComponent: 'IAPManagementPanel',
    executive: {
      tabId: 'iap',
      label: 'In-App Purchases',
      icon: 'phone-portrait',
      route: '/executive-dashboard?section=iap',
      categoryId: 'revenue',
      i18nKey: 'executive.section.iap-management',
      permissionGate: 'admin-only',
      featureFlags: [],
    },
    operations: {
      tabId: 'iap',
      label: 'In-App Purchases',
      icon: 'phone-portrait',
      route: '/admin-console?category=finance&tab=iap',
      categoryId: 'finance',
      i18nKey: null,
      permissionGate: 'admin-or-operations-manager',
      featureFlags: [],
    },
  },
];

const CAPABILITY_MAP: Record<SharedCapabilityId, SharedCapabilityContract> = SHARED_CONSOLE_CAPABILITIES.reduce(
  (acc, item) => {
    acc[item.capabilityId] = item;
    return acc;
  },
  {} as Record<SharedCapabilityId, SharedCapabilityContract>,
);

export const getSharedExecutiveTab = (capabilityId: SharedCapabilityId) => {
  const tab = CAPABILITY_MAP[capabilityId].executive;
  return { id: tab.tabId, label: tab.label, icon: tab.icon };
};

export const getSharedOperationsTab = (capabilityId: SharedCapabilityId) => {
  const tab = CAPABILITY_MAP[capabilityId].operations;
  return { id: tab.tabId, label: tab.label, icon: tab.icon };
};

export const EXEC_SECTION_ALIASES_FROM_OPERATIONS: Record<string, string> = SHARED_CONSOLE_CAPABILITIES.reduce(
  (acc, item) => {
    if (item.operations.tabId !== item.executive.tabId) {
      acc[item.operations.tabId] = item.executive.tabId;
    }
    return acc;
  },
  {} as Record<string, string>,
);

// Batch-1 backward-compatible aliases for historical executive section IDs.
export const EXEC_SECTION_LEGACY_ALIASES: Record<string, string> = {
  otp: 'otp-delivery',
  newsletter: 'newsletter-analytics',
  'iap-management': 'iap',
  'llm-billing': 'llm-usage-billing',
  'ai-features': 'ai-analytics-link',
  'ai-usage': 'ai-analytics-link',
};
