import React, { useEffect, useState, useCallback, lazy, useMemo } from 'react';
import { View, Text, ScrollView, TouchableOpacity, Platform, useWindowDimensions, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import AppShell from './AppShell';
import api from '../services/api';
import { trackTabAliasHit } from '../services/tabAliasTelemetry';
import DataFreshnessIndicator from './DataFreshnessIndicator';
import GtecComplianceBadge from './admin/GtecComplianceBadge';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { useRealtime } from '../context/RealtimeContext';
import { useTranslation } from '../hooks/useTranslation';
import { hasAdminConsoleVisibility } from '../utils/adminAccess';

import { CATEGORIES, OperationsCommandPalette, OperationsToastAlerts, OperationsCategoryBar, getCategoryColor } from '../components/operations-console/OperationsConsoleExtracted';
import { ThemeComplianceWidget } from './admin/ThemeComplianceWidget';
import { TopThemeOffendersLeaderboard } from './admin/TopThemeOffendersLeaderboard';
import { V7TemplateComplianceWidget } from './admin/V7TemplateComplianceWidget';
import TopBrokenPanelsWidget from './admin/TopBrokenPanelsWidget';
import AdminHealthDigestWidget from './admin/AdminHealthDigestWidget';
import GlobalParityAuditCard from './admin/GlobalParityAuditCard';
import PreviewBrowserE2ECard from './admin/PreviewBrowserE2ECard';
import PreviewFreshnessCard from './admin/PreviewFreshnessCard';
import EntitlementDriftAuditCard from './admin/EntitlementDriftAuditCard';
import { AudioStudioConversionCard } from './admin/AudioStudioConversionCard';
import { PodcastsConversionCard } from './admin/PodcastsConversionCard';
import { SportsConversionCard } from './admin/SportsConversionCard';
import { ErrorBoundary } from './ErrorBoundary';
import {
  DEFAULT_STARTUP_RECOVERY_DELAY_MS,
  STARTUP_RECOVERY_DELAY_KEY,
  STARTUP_RECOVERY_DELAY_OPTIONS,
  normalizeStartupRecoveryDelay,
} from '../constants/startupRecovery';
import TabMergeHubPanel from './admin/TabMergeHubPanel';
import {
  OPERATIONS_LEGACY_TAB_TO_HUB,
  getOperationsHubById,
} from '../config/phaseBTabConsolidation';
import { SectionProgressRail } from './progress/SectionProgressRail';
import { handleAppRecoverableError } from '../utils/appRecoverableError';

/* ── Lazy-loaded admin panels (deferred until selected) ── */
const ExecutiveDashboardPanel = lazy(() => import('./admin/ExecutiveDashboardPanel'));
const LiveActivityFeedPanel = lazy(() => import('./admin/LiveActivityFeedPanel'));
const HiringAnalyticsPanel = lazy(() => import('./admin/HiringAnalyticsPanel'));
const WhiteLabelPanel = lazy(() => import('./admin/WhiteLabelPanel'));
const TeamsPanel = lazy(() => import('./admin/TeamsPanel'));
const LanguagesPanel = lazy(() => import('./admin/LanguagesPanel'));
const LanguageQualityDashboardPanel = lazy(() => import('./admin/LanguageQualityDashboardPanel'));
const TranslationCoverageDashboard = lazy(() => import('./admin/TranslationCoverageDashboard'));
const TranslationQualityReview = lazy(() => import('./admin/TranslationQualityReview'));
const CampaignDashboardPanel = lazy(() => import('./admin/CampaignDashboardPanel'));
const ExecutiveQualityDashboardPanel = lazy(() => import('./admin/ExecutiveQualityDashboardPanel'));
const TeamAnalyticsPanel = lazy(() => import('./admin/TeamAnalyticsPanel'));
const AccessMatrixPanel = lazy(() => import('./admin/AccessMatrixPanel'));
const WebhookReplayPanel = lazy(() => import('./admin/WebhookReplayPanel'));
const FAQManagementPanel = lazy(() => import('./admin/FAQManagementPanel'));
const AdminNotificationHistoryPanel = lazy(() => import('./admin/AdminNotificationHistoryPanel'));
const AIResolutionDashboard = lazy(() => import('./admin/AIResolutionDashboard'));
const TicketAssignmentPanel = lazy(() => import('./admin/TicketAssignmentPanel'));
const EscalationPanel = lazy(() => import('./admin/EscalationPanel'));
const UserInsightsPanel = lazy(() => import('./admin/UserInsightsPanel'));
const SelfRepairPanel = lazy(() => import('./admin/SelfRepairPanel'));
const AutoScalingPanel = lazy(() => import('./admin/AutoScalingPanel'));
const OperationsDashboard = lazy(() => import('./admin/OperationsDashboard'));
const UBADashboardPanel = lazy(() => import('./admin/UBADashboardPanel'));
const SessionReplayPanel = lazy(() => import('./admin/SessionReplayPanel'));
const SecurityRecommendationsPanel = lazy(() => import('./admin/SecurityRecommendationsPanel'));
const SecurityPosturePanel = lazy(() => import('./admin/SecurityPosturePanel'));
const MFASettingsPanel = lazy(() => import('./admin/MFASettingsPanel'));
const ReferralAnalyticsPanel = lazy(() => import('./admin/ReferralAnalyticsPanel'));
const ChurnRecoveryPanel = lazy(() => import('./admin/ChurnRecoveryPanel'));
const NovaAnalyticsPanel = lazy(() => import('./admin/NovaAnalyticsPanel'));
const ChangelogAdminPanel = lazy(() => import('./admin/ChangelogAdminPanel'));
const ReengagementPanel = lazy(() => import('./admin/ReengagementPanel'));
const ABTestingPanel = lazy(() => import('./admin/ABTestingPanel'));
const ABPerformanceDashboard = lazy(() => import('./admin/ABPerformanceDashboard'));
const PlatformAnalyticsPanel = lazy(() => import('./admin/PlatformAnalyticsPanel'));
const CodeHealthPanel = lazy(() => import('./admin/CodeHealthPanel'));
const AccessibilityPanel = lazy(() => import('./admin/AccessibilityPanel'));
const FeatureManagerPanel = lazy(() => import('./admin/FeatureManagerPanel'));
const DashboardLayoutManager = lazy(() => import('./admin/DashboardLayoutManager'));
const EmailTemplatesPanel = lazy(() => import('./admin/EmailTemplatesPanel'));
const BookingCommandCenter = lazy(() => import('./admin/BookingCommandCenter'));
const SystemHealthPanel = lazy(() => import('./admin/SystemHealthPanel'));
const PlatformIntegrationsDashboard = lazy(() => import('./admin/PlatformIntegrationsDashboard').then((module) => ({ default: module.PlatformIntegrationsDashboard })));
const LLMUsageBillingDashboard = lazy(() => import('./admin/LLMUsageBillingDashboard').then((module) => ({ default: module.LLMUsageBillingDashboard })));
const BatchAIPanel = lazy(() => import('./admin/BatchAIPanel'));
const HelpDeskPanel = lazy(() => import('./admin/SupportTicketsPanel'));
const SEODashboardPanel = lazy(() => import('./admin/SEODashboardPanel'));
const AutomationEnginePanel = lazy(() => import('./admin/AutomationEnginePanel'));
const CriticalJourneyMonitorPanel = lazy(() => import('./admin/CriticalJourneyMonitorPanel'));
const AIInsightsPanel = lazy(() => import('./admin/AIInsightsPanel'));
const EnterpriseSecurityPanel = lazy(() => import('./admin/EnterpriseSecurityPanel'));
const ThreatDetectionPanel = lazy(() => import('./admin/ThreatDetectionPanel'));
const DeploymentOrchestrationPanel = lazy(() => import('./admin/DeploymentOrchestrationPanel'));
const RealityValidationPanel = lazy(() => import('./admin/RealityValidationPanel'));
const AppStoreConnectPanel = lazy(() => import('./admin/AppStoreConnectPanel'));
const GooglePlayPanel = lazy(() => import('./admin/GooglePlayPanel'));
const UnifiedASOPanel = lazy(() => import('./admin/UnifiedASOPanel'));
const PerfAdvisorPanel = lazy(() => import('./admin/PerfAdvisorPanel'));
const AIRemediationPanel = lazy(() => import('./admin/AIRemediationPanel'));
const AutoDetectPanel = lazy(() => import('./admin/AutoDetectPanel'));
const SSOStatusPanel = lazy(() => import('./admin/SSOStatusPanel'));
const WebVitalsPanel = lazy(() => import('./admin/WebVitalsPanel'));
const PerformanceGuardianPanel = lazy(() => import('./admin/PerformanceGuardianPanel'));
const GoogleVerificationPanel = lazy(() => import('./admin/GoogleVerificationPanel'));
const NewsletterAnalyticsPanel = lazy(() => import('./admin/NewsletterAnalyticsPanelV2'));
const SubscriberGrowthPanel = lazy(() => import('./admin/SubscriberGrowthPanel'));
const CareerApplicationsPanel = lazy(() => import('./admin/CareerApplicationsPanel'));
const ContactSubmissionsPanel = lazy(() => import('./admin/ContactSubmissionsPanel'));
const AnomalyDetectionPanel = lazy(() => import('./admin/AnomalyDetectionPanel'));
const PaymentsTaxPanel = lazy(() => import('./admin/PaymentsTaxPanel'));
const ProviderIncidentTimelinePanel = lazy(() => import('./admin/ProviderIncidentTimelinePanel'));
const IAPManagementPanel = lazy(() => import('./admin/IAPManagementPanel'));
const AIPlatformIntegrityPanel = lazy(() => import('./admin/AIPlatformIntegrityPanel'));
const PlatformHealthPanel = lazy(() => import('./admin/PlatformHealthPanel'));
const PlatformTrustCenterPanel = lazy(() => import('./admin/PlatformTrustCenterPanel'));
const ZeroTrustCenterPanel = lazy(() => import('./admin/ZeroTrustCenterPanel'));
const WAFFirewallPanel = lazy(() => import('./admin/WAFFirewallPanel'));
const NotificationRulesPanel = lazy(() => import('./admin/NotificationRulesPanel'));
const ReceiptBrandingPanel = lazy(() => import('./admin/ReceiptBrandingPanel'));
const PaymentRecoveryPanel = lazy(() => import('./admin/PaymentRecoveryPanel'));
const AICommandCenterPanel = lazy(() => import('./admin/AICommandCenterPanel'));
const EnterpriseControlPlanePanel = lazy(() => import('./admin/EnterpriseControlPlanePanel'));
const AILearningHubInsightsPanel = lazy(() => import('./admin/AILearningHubInsightsPanel'));
const CertificateAnalyticsPanel = lazy(() => import('./admin/CertificateAnalyticsPanel'));
const CertificateTemplateManagerPanel = lazy(() => import('./admin/CertificateTemplateManagerPanel'));
const AuthComplianceDashboardPanel = lazy(() => import('./admin/AuthComplianceDashboardPanel'));
const AutonomousEnginePanel = lazy(() => import('./admin/AutonomousEnginePanel'));
const PlatformSettingsPanel = lazy(() => import('./admin/PlatformSettingsPanel'));
const ThemeValidationDashboard = lazy(() => import('./admin/ThemeValidationDashboard'));
const ThemeGovernanceDashboard = lazy(() => import('./admin/ThemeGovernanceDashboard'));
const ThemeAuditPanel = lazy(() => import('./admin/ThemeAuditPanel'));
const OTPDeliveryDashboardPanel = lazy(() => import('./admin/OTPDeliveryDashboardPanel'));
const TosManagementPanel = lazy(() => import('./admin/TosManagementPanel'));
const SecurityIncidentDashboard = lazy(() => import('./admin/SecurityIncidentDashboard'));
const ZeroTrustRootCauseBoard = lazy(() => import('./admin/ZeroTrustRootCauseBoard'));
const LegalNoticeBroadcastPanel = lazy(() => import('./admin/LegalNoticeBroadcastPanel'));
const CookiePolicyBroadcastPanel = lazy(() => import('./admin/CookiePolicyBroadcastPanel'));
const PrivacyPolicyBroadcastPanel = lazy(() => import('./admin/PrivacyPolicyBroadcastPanel'));
const SecurityIncidentBroadcastPanel = lazy(() => import('./admin/SecurityIncidentBroadcastPanel'));
const GpsStateManagementPanel = lazy(() => import('./admin/GpsStateManagementPanel'));
const LegalUpdateEnterpriseWorkspace = lazy(() => import('./executive/LegalUpdateEnterpriseWorkspace'));
const EmailGuardrailControlCenterWorkspace = lazy(() => import('./executive/EmailGuardrailControlCenterWorkspace'));
const AssignedHostControlCenterPanel = lazy(() => import('./admin/AssignedHostControlCenterPanel'));
const GtecScanV2Panel = lazy(() => import('./admin/GtecScanV2Panel'));
const GtecUpstreamWatchdogPanel = lazy(() => import('./admin/GtecUpstreamWatchdogPanel'));
const SportsSourceHealthOpsPanel = lazy(() => import('./admin/SportsSourceHealthOpsPanel').then((module) => ({ default: module.SportsSourceHealthOpsPanel })));
const MatchdayRemindersOpsPanel = lazy(() => import('./admin/MatchdayRemindersOpsPanel').then((module) => ({ default: module.MatchdayRemindersOpsPanel })));
const ContentIntegrityOpsPanel = lazy(() => import('./admin/ContentIntegrityOpsPanel').then((module) => ({ default: module.ContentIntegrityOpsPanel })));
const BlogEditorialPanel = lazy(() => import('./operations-console/BlogEditorialPanel').then((module) => ({ default: module.BlogEditorialPanel })));
const TalentNetworkAdminPanel = lazy(() => import('./admin/TalentNetworkAdminPanel').then((module) => ({ default: module.TalentNetworkAdminPanel })));
const EntitlementDriftAuditPanel = lazy(() => import('./admin/EntitlementDriftAuditPanel'));

/* ── Custom Dashboards wrapper ── */
function CustomDashboardsPanel({ colors }: { colors: any }) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const [activeType, setActiveType] = useState<'executive' | 'admin'>('executive');
  const types = [
    { id: 'executive' as const, label: tx('operationsConsole.customDashboards.executive', 'Executive'), icon: 'grid' },
    { id: 'admin' as const, label: tx('operationsConsole.customDashboards.admin', 'Admin'), icon: 'settings' },
  ];
  return (
    <View style={{ flex: 1, padding: 16 }} data-testid="custom-dashboards-panel" testID="custom-dashboards-panel">
      <Text style={{ fontSize: 18, fontWeight: '700', color: colors.text, marginBottom: 12 }}>{tx('operationsConsole.customDashboards.title', 'Dashboard Layout Manager')}</Text>
      <Text style={{ fontSize: 13, color: colors.textMuted, marginBottom: 16 }}>{tx('operationsConsole.customDashboards.subtitle', 'Customize widget visibility, order, and size for each dashboard type.')}</Text>
      <View style={{ flexDirection: 'row', gap: 8, marginBottom: 20 }}>
        {types.map(t => (
          <TouchableOpacity key={t.id} onPress={() => setActiveType(t.id)}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, backgroundColor: activeType === t.id ? colors.primary : colors.surface, borderWidth: 1, borderColor: activeType === t.id ? colors.primary : colors.border }}
            data-testid={`dashboard-type-${t.id}`} testID={`dashboard-type-${t.id}`}>
            <Ionicons name={t.icon as any} size={14} color={activeType === t.id ? colors.primaryText : colors.textMuted} />
            <Text style={{ fontSize: 13, fontWeight: '600', color: activeType === t.id ? colors.primaryText : 'var(--app-text)' }}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <DashboardLayoutManager dashboardType={activeType} colors={colors} />
    </View>
  );
}

function AdminPanelFallback({ tabId, colors, onNavigate }: { tabId: string; colors: any; onNavigate: (tabId: string) => void }) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  return (
    <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 16 }} data-testid="admin-console-panel-fallback" testID="admin-console-panel-fallback">
      <Text style={{ color: colors.text, fontSize: 16, fontWeight: '800' }} data-testid="admin-console-panel-fallback-title" testID="admin-console-panel-fallback-title">{tx('operationsConsole.fallback.title', 'Panel unavailable')}</Text>
      <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 8, lineHeight: 18 }} data-testid="admin-console-panel-fallback-description" testID="admin-console-panel-fallback-description">
        {tx('operationsConsole.fallback.description', 'The selected admin tab `{tabId}` has no active renderer right now. We prevented a blank screen and moved recovery controls here.').replace('{tabId}', tabId)}
      </Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        <TouchableOpacity onPress={() => onNavigate('ai-command-center')} style={{ backgroundColor: colors.primary, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="admin-console-panel-fallback-open-command-center" testID="admin-console-panel-fallback-open-command-center">
          <Text style={{ color: colors.primaryText, fontSize: 11, fontWeight: '800' }}>{tx('operationsConsole.fallback.openAiCommandCenter', 'Open AI Command Center')}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => onNavigate('ops-command-center')} style={{ backgroundColor: colors.surface || colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="admin-console-panel-fallback-open-operations-center" testID="admin-console-panel-fallback-open-operations-center">
          <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>{tx('operationsConsole.fallback.openOperationsCenter', 'Open Operations Center')}</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

/* ── Panel renderer (memoized to prevent unnecessary re-renders) ── */
const PanelContent = React.memo(function PanelContent({ tabId, colors, darkMode, onNavigate }: { tabId: string; colors: any; darkMode: boolean; onNavigate: (tabId: string) => void }) {
  const hub = getOperationsHubById(tabId);
  if (hub) {
    return (
      <TabMergeHubPanel
        colors={colors}
        hub={hub}
        onOpenLegacyTab={(legacyTab) => onNavigate(legacyTab.id)}
      />
    );
  }

  switch (tabId) {
    case 'dashboard': return <ExecutiveDashboardPanel colors={colors} />;
    case 'ai-command-center': return <AICommandCenterPanel colors={colors} onNavigate={onNavigate} />;
    case 'ai-learning-hub-insights': return <AILearningHubInsightsPanel colors={colors} darkMode={darkMode} />;
    case 'certificate-analytics': return <CertificateAnalyticsPanel colors={colors} darkMode={darkMode} />;
    case 'certificate-template-manager': return <CertificateTemplateManagerPanel colors={colors} />;
    case 'auth-compliance-dashboard': return <AuthComplianceDashboardPanel colors={colors} darkMode={darkMode} />;
    case 'live-activity': return <LiveActivityFeedPanel colors={colors} />;
    case 'custom-dashboards': return <CustomDashboardsPanel colors={colors} />;
    case 'teams': return <TeamsPanel colors={colors} />;
    case 'user-insights': return <UserInsightsPanel colors={colors} />;
    case 'reengagement': return <ReengagementPanel colors={colors} />;
    case 'booking-center': return <BookingCommandCenter colors={colors} />;
    case 'hiring-analytics': return <HiringAnalyticsPanel colors={colors} />;
    case 'career-applications': return <CareerApplicationsPanel colors={colors} />;
    case 'talent-network-admin': return <TalentNetworkAdminPanel colors={colors} />;
    case 'helpdesk': return <HelpDeskPanel colors={colors} />;
    case 'ticket-assignment': return <TicketAssignmentPanel colors={colors} />;
    case 'escalation': return <EscalationPanel colors={colors} />;
    case 'faq-mgmt': return <FAQManagementPanel colors={colors} />;
    case 'contact-submissions': return <ContactSubmissionsPanel colors={colors} />;
    case 'churn-recovery': return <ChurnRecoveryPanel />;
    case 'seo-dashboard': return <SEODashboardPanel colors={colors} />;
    case 'ai-insights': return <AIInsightsPanel colors={colors} />;
    case 'platform-analytics': return <PlatformAnalyticsPanel colors={colors} />;
    case 'ai-resolution': return <AIResolutionDashboard colors={colors} />;
    case 'team-analytics': return <TeamAnalyticsPanel colors={colors} />;
    case 'uba-dashboard': return <UBADashboardPanel colors={colors} />;
    case 'referral-analytics': return <ReferralAnalyticsPanel />;
    case 'nova-analytics': return <NovaAnalyticsPanel />;
    case 'campaign-dashboard': return <CampaignDashboardPanel colors={colors} />;
    case 'ops-dashboard': return <OperationsDashboard />;
    case 'enterprise-control-plane': return <EnterpriseControlPlanePanel />;
    case 'feature-manager': return <FeatureManagerPanel colors={colors} />;
    case 'gps-state-management': return <GpsStateManagementPanel colors={colors} />;
    case 'automation-engine': return <AutomationEnginePanel colors={colors} />;
    case 'critical-journey-monitor': return <CriticalJourneyMonitorPanel colors={colors} />;
    case 'auto-scaling': return <AutoScalingPanel colors={colors} />;
    case 'self-repair': return <SelfRepairPanel colors={colors} />;
    case 'system-health': return <SystemHealthPanel colors={colors} />;
    case 'platform-integrations': return <PlatformIntegrationsDashboard />;
    case 'llm-usage-billing': return <LLMUsageBillingDashboard />;
    case 'session-replay': return <SessionReplayPanel colors={colors} />;
    case 'changelog-mgmt': return <ChangelogAdminPanel colors={colors} />;
    case 'access-matrix': return <AccessMatrixPanel colors={colors} />;
    case 'security-recs': return <SecurityRecommendationsPanel colors={colors} />;
    case 'security-posture': return <SecurityPosturePanel colors={colors} />;
    case 'enterprise-security': return <EnterpriseSecurityPanel colors={colors} />;
    case 'threat-detection': return <ThreatDetectionPanel colors={colors} />;
    case 'deployment-orchestration': return <DeploymentOrchestrationPanel colors={colors} />;
    case 'reality-validation': return <RealityValidationPanel colors={colors} />;
    case 'appstore-connect': return <AppStoreConnectPanel colors={colors} />;
    case 'google-play': return <GooglePlayPanel colors={colors} />;
    case 'unified-aso': return <UnifiedASOPanel colors={colors} />;
    case 'perf-advisor': return <PerfAdvisorPanel colors={colors} />;
    case 'ai-remediation': return <AIRemediationPanel colors={colors} />;
    case 'auto-detect': return <AutoDetectPanel colors={colors} />;
    case 'mfa-settings': return <MFASettingsPanel colors={colors} />;
    case 'sso-status': return <SSOStatusPanel colors={colors} />;
    case 'web-vitals': return <WebVitalsPanel colors={colors} />;
    case 'performance-guardian': return <PerformanceGuardianPanel colors={colors} darkMode={darkMode} />;
    case 'google-verification': return <GoogleVerificationPanel colors={colors} />;
    case 'newsletter-analytics': return <NewsletterAnalyticsPanel colors={colors} />;
    case 'subscriber-growth': return <SubscriberGrowthPanel colors={colors} />;
    case 'email-templates': return <EmailTemplatesPanel colors={colors} initialTab="templates" />;
    case 'email-reliability': return <EmailTemplatesPanel colors={colors} initialTab="reliability" />;
    case 'languages': return <><LanguageQualityDashboardPanel colors={colors} /><LanguagesPanel colors={colors} /><View style={{ marginTop: 24 }}><TranslationCoverageDashboard colors={colors} /></View><View style={{ marginTop: 24 }}><TranslationQualityReview colors={colors} /></View></>;
    case 'whitelabel': return <WhiteLabelPanel colors={colors} />;
    case 'webhook-replay': return <WebhookReplayPanel colors={colors} darkMode={darkMode} />;
    case 'ab-testing': return <ABTestingPanel colors={colors} />;
    case 'ab-performance': return <ABPerformanceDashboard colors={colors} />;
    case 'batch-ai': return <BatchAIPanel colors={colors} />;
    case 'code-health': return <CodeHealthPanel colors={colors} />;
    case 'entitlement-drift-audit': return <EntitlementDriftAuditPanel colors={colors} />;
    case 'accessibility': return <AccessibilityPanel colors={colors} />;
    case 'anomaly-detection': return <AnomalyDetectionPanel colors={colors} />;
    case 'executive-quality-dashboard': return <ExecutiveQualityDashboardPanel colors={colors} />;
    case 'payments-tax': return <PaymentsTaxPanel colors={colors} />;
    case 'provider-incidents': return <ProviderIncidentTimelinePanel colors={colors} />;
    case 'iap': return <IAPManagementPanel />;
    case 'ai-platform-integrity': return <AIPlatformIntegrityPanel colors={colors} />;
    case 'platform-health': return <PlatformHealthPanel colors={colors} />;
    case 'platform-settings': return <PlatformSettingsPanel />;
    case 'theme-validation': return <ThemeValidationDashboard />;
    case 'theme-governance-dashboard': return <ThemeGovernanceDashboard />;
    case 'theme-audit': return <ThemeAuditPanel />;
    case 'otp-delivery': return <OTPDeliveryDashboardPanel colors={colors} />;
    case 'sports-source-health': return <SportsSourceHealthOpsPanel colors={colors} />;
    case 'matchday-reminders': return <MatchdayRemindersOpsPanel colors={colors} />;
    case 'content-integrity': return <ContentIntegrityOpsPanel colors={colors} />;
    case 'blog-editorial': return <BlogEditorialPanel colors={colors} />;
    case 'zero-trust-center': return <ZeroTrustCenterPanel colors={colors} />;
    case 'zero-trust-root-cause-board': return <ZeroTrustRootCauseBoard />;
    case 'platform-trust-center': return <PlatformTrustCenterPanel colors={colors} />;
    case 'waf-firewall': return <WAFFirewallPanel colors={colors} />;
    case 'notification-rules': return <NotificationRulesPanel />;
    case 'receipt-branding': return <ReceiptBrandingPanel colors={colors} />;
    case 'payment-recovery': return <PaymentRecoveryPanel colors={colors} />;
    case 'notification-history': return <AdminNotificationHistoryPanel colors={colors} />;
    case 'autonomous-engine': return <AutonomousEnginePanel />;
    case 'tos-management': return <TosManagementPanel />;
    case 'security-incidents': return <SecurityIncidentDashboard />;
    case 'gtec':
      return (
        <View style={{ gap: 12 }} data-testid="gtec-section" testID="gtec-section">
          <View data-testid="gtec-scan-v2-section" testID="gtec-scan-v2-section">
            <GtecScanV2Panel />
          </View>
          <View data-testid="gtec-upstream-watchdog-section" testID="gtec-upstream-watchdog-section">
            <GtecUpstreamWatchdogPanel />
          </View>
        </View>
      );
    case 'legal-notice-broadcast': return <LegalNoticeBroadcastPanel />;
    case 'legal-update': return <LegalUpdateEnterpriseWorkspace />;
    case 'assigned-host': return <AssignedHostControlCenterPanel colors={colors} />;
    case 'email-guardrail-control-center': return <EmailGuardrailControlCenterWorkspace />;
    case 'cookie-policy-broadcast': return <CookiePolicyBroadcastPanel />;
    case 'privacy-policy-broadcast': return <PrivacyPolicyBroadcastPanel />;
    case 'security-incident-broadcast': return <SecurityIncidentBroadcastPanel />;
    default: return <AdminPanelFallback tabId={tabId} colors={colors} onNavigate={onNavigate} />;
  }
});

const TAB_ALIASES: Record<string, string> = {
  'payments-tax-intelligence': 'payments-tax',
  'in-app-purchases': 'iap',
  'auth-compliance': 'auth-compliance-dashboard',
  'zero-trust': 'zero-trust-center',
  ...OPERATIONS_LEGACY_TAB_TO_HUB,
  gtec: 'gtec',
  'iap-management': 'iap',
  newsletter: 'newsletter-analytics',
  otp: 'otp-delivery',
  'llm-billing': 'llm-usage-billing',
  'ai-features': 'ai-insights',
  'ai-usage': 'ai-insights',
  'entitlement-drift': 'entitlement-drift-audit',
  'assigned-host-control-center': 'assigned-host',
  'assigned-host-monitor': 'assigned-host',
};

const DIRECT_RENDER_LEGACY_TABS = new Set<string>(['gtec', 'entitlement-drift-audit']);

const DIRECT_RENDER_TAB_META: Record<string, { label: string; icon: string }> = {
  gtec: { label: 'GTEC', icon: 'shield-checkmark' },
  'entitlement-drift-audit': { label: 'Entitlement Drift Audit', icon: 'git-compare' },
};

function normalizeOperationsTabId(tabId: string): string {
  const raw = String(tabId || '').trim();
  if (!raw) return '';
  if (DIRECT_RENDER_LEGACY_TABS.has(raw)) return raw;
  const aliased = TAB_ALIASES[raw] || raw;
  if (DIRECT_RENDER_LEGACY_TABS.has(aliased)) return aliased;
  return OPERATIONS_LEGACY_TAB_TO_HUB[aliased] || aliased;
}

// Hardcoded category mapping for DIRECT_RENDER_LEGACY_TABS that are not in OPERATIONS_LEGACY_TAB_TO_HUB
const DIRECT_RENDER_TAB_CATEGORY_MAP: Record<string, string> = {
  gtec: 'security',
  'entitlement-drift-audit': 'platform',
};

function resolveOperationsCategoryForTab(tabId: string): string | null {
  const normalized = normalizeOperationsTabId(tabId);
  
  // Check if this is a direct-render legacy tab with hardcoded category
  if (DIRECT_RENDER_LEGACY_TABS.has(normalized) && DIRECT_RENDER_TAB_CATEGORY_MAP[normalized]) {
    return DIRECT_RENDER_TAB_CATEGORY_MAP[normalized];
  }
  
  const directCategory = CATEGORIES.find((cat) => cat.tabs.some((tab) => tab.id === normalized))?.id;
  if (directCategory) return directCategory;

  const hubId = OPERATIONS_LEGACY_TAB_TO_HUB[normalized] || OPERATIONS_LEGACY_TAB_TO_HUB[String(tabId || '').trim()];
  if (!hubId) return null;
  return CATEGORIES.find((cat) => cat.tabs.some((tab) => tab.id === hubId))?.id || null;
}

type DuplicationDriftSeverity = 'none' | 'low' | 'medium' | 'high' | 'critical';

interface DuplicationDriftImpact {
  mode: 'exact' | 'near';
  dataset: string;
  label: string;
  occurrences: number;
  sample_ids: string[];
  fingerprint: string;
}

interface DuplicationDriftResponse {
  generated_at: string;
  thresholds: { low_pct: number; medium_pct: number; high_pct: number };
  overall: {
    datasets_covered: number;
    total_records_scanned: number;
    exact_duplicate_records: number;
    near_duplicate_records: number;
    combined_duplicate_records: number;
    combined_drift_rate_pct: number;
    severity: DuplicationDriftSeverity;
    requires_attention: boolean;
  };
  impacted_records: DuplicationDriftImpact[];
  last_acknowledged?: {
    acknowledged_at?: string;
    acknowledged_by?: string;
    note?: string;
  } | null;
}

const getInitialAdminConsoleSelection = () => {
  const fallback = {
    activeCategory: 'overview',
    activeTab: 'ops-command-center',
    urlSearch: '',
  };

  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return fallback;
  }

  try {
    const urlSearch = window.location.search || '';
    const params = new URLSearchParams(urlSearch);
    const categoryParam = (params.get('category') || '').trim();
    const tabParam = (params.get('tab') || '').trim();
    const normalizedTabParam = normalizeOperationsTabId(tabParam);
    const matchedTabCategory = normalizedTabParam
      ? resolveOperationsCategoryForTab(normalizedTabParam)
      : null;

    let activeCategory = fallback.activeCategory;
    let activeTab = fallback.activeTab;

    if (matchedTabCategory && normalizedTabParam) {
      activeCategory = matchedTabCategory;
      activeTab = normalizedTabParam;
    }

    if (categoryParam) {
      const matchedCategory = CATEGORIES.find((cat) => cat.id === categoryParam);
      if (matchedCategory) {
        const categoryHasRequestedTab = normalizedTabParam
          ? matchedCategory.tabs.some((tab) => tab.id === normalizedTabParam)
          : false;

        if (!normalizedTabParam || categoryHasRequestedTab) {
          activeCategory = matchedCategory.id;
          // Preserve direct-render legacy tabs even if not in CATEGORIES.tabs
          const isDirectRenderTab = DIRECT_RENDER_LEGACY_TABS.has(activeTab);
          if (!isDirectRenderTab && !matchedCategory.tabs.some((tab) => tab.id === activeTab)) {
            activeTab = matchedCategory.tabs[0]?.id || activeTab;
          }
        } else if (matchedTabCategory && normalizedTabParam) {
          activeCategory = matchedTabCategory;
          activeTab = normalizedTabParam;
        }
      }
    }

    return {
      activeCategory,
      activeTab,
      urlSearch,
    };
  } catch {
    return fallback;
  }
};

export default function OperationsConsoleView() {
  const { user, loading } = useAuth();
  const { darkMode, setThemeMode , colors} = useTheme();
  const { width } = useWindowDimensions();
  const router = useRouter();
  const { subscribeType } = useRealtime();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const operationsTitle = t('operationsConsole.header.title');
  const initialConsoleSelection = useMemo(() => getInitialAdminConsoleSelection(), []);
  const hasSessionTokenHint = useMemo(() => {
    if (typeof window === 'undefined') return false;
    try {
      return Boolean(window.localStorage.getItem('session_token'));
    } catch {
      return false;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email, user?.role]);

  const hasAdminAccess = hasAdminConsoleVisibility(user);
  const [activeCategory, setActiveCategory] = useState(initialConsoleSelection.activeCategory);
  const [activeTab, setActiveTab] = useState(initialConsoleSelection.activeTab);
  const aliasTelemetrySeenRef = React.useRef<Record<string, boolean>>({});
  const emitAliasTelemetry = useCallback((sourceTabId: string, canonicalTabId: string, context: string) => {
    const source = String(sourceTabId || '').trim();
    const canonical = String(canonicalTabId || '').trim();
    if (!source || !canonical || source === canonical) return;
    const key = `operations:${source}->${canonical}:${context}`;
    if (aliasTelemetrySeenRef.current[key]) return;
    aliasTelemetrySeenRef.current[key] = true;
    trackTabAliasHit({
      console: 'operations',
      source_tab_id: source,
      canonical_tab_id: canonical,
      context,
    }).catch(() => {});
  }, []);
  const canonicalActiveTab = useMemo(
    () => {
      const normalized = normalizeOperationsTabId(activeTab);
      if (DIRECT_RENDER_LEGACY_TABS.has(normalized)) {
        return OPERATIONS_LEGACY_TAB_TO_HUB[normalized] || normalized;
      }
      return normalized;
    },
    [activeTab],
  );

  const [urlSearch, setUrlSearch] = useState(initialConsoleSelection.urlSearch);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [debugAdvancedMode, setDebugAdvancedMode] = useState(false);
  const [pinnedTabs, setPinnedTabs] = useState<string[]>([]);
  const [panelReady, setPanelReady] = useState(false);
  const [startupRecoveryDelayMs, setStartupRecoveryDelayMs] = useState(DEFAULT_STARTUP_RECOVERY_DELAY_MS);

  // Notifications
  const [liveNotifications, setLiveNotifications] = useState<any[]>([]);
  const [notifCounts, setNotifCounts] = useState<any>({ total: 0 });
  // Command palette
  const [cmdOpen, setCmdOpen] = useState(false);
  const [adminLastUpdated, setAdminLastUpdated] = useState<Date | null>(null);
  const [duplicationDrift, setDuplicationDrift] = useState<DuplicationDriftResponse | null>(null);
  const [duplicationDriftLoading, setDuplicationDriftLoading] = useState(false);
  const [duplicationDriftExpanded, setDuplicationDriftExpanded] = useState(false);
  const [duplicationDriftAckLoading, setDuplicationDriftAckLoading] = useState(false);

  const resolveCategoryForTab = useCallback((tabId: string) => {
    return resolveOperationsCategoryForTab(tabId);
  }, []);

  // Build flat list of all searchable items
  const allItems = CATEGORIES.flatMap(cat =>
    cat.tabs.map(tab => ({ catId: cat.id, catLabel: cat.label, catColor: getCategoryColor(cat, colors), ...tab }))
  );
  const directRenderActiveItem = DIRECT_RENDER_TAB_META[canonicalActiveTab]
    ? {
      catId: activeCategory,
      catLabel: activeCategory,
      catColor: colors.primary,
      id: canonicalActiveTab,
      ...DIRECT_RENDER_TAB_META[canonicalActiveTab],
    }
    : null;
  const activeItem = allItems.find(i => i.id === canonicalActiveTab) || allItems.find(i => i.id === activeTab) || directRenderActiveItem;
  const pinnedItems = allItems.filter(i => pinnedTabs.includes(i.id));

  const openCmd = useCallback(() => { setCmdOpen(true); }, []);
  const closeCmd = useCallback(() => { setCmdOpen(false); }, []);

  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem('admin_console_pinned_tabs');
        if (stored) {
          const rawParsed = JSON.parse(stored);
          const parsed = Array.isArray(rawParsed) ? rawParsed : [];
          const normalized = Array.from(new Set(parsed
            .map((id: string) => normalizeOperationsTabId(id))
            .filter((id: string) => !!resolveCategoryForTab(id))));
          setPinnedTabs(normalized);
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    })();
  }, [resolveCategoryForTab]);

  useEffect(() => {
    (async () => {
      try {
        const localValue = Platform.OS === 'web' && typeof window !== 'undefined'
          ? window.localStorage.getItem(STARTUP_RECOVERY_DELAY_KEY)
          : null;
        const stored = localValue || await AsyncStorage.getItem(STARTUP_RECOVERY_DELAY_KEY);
        setStartupRecoveryDelayMs(normalizeStartupRecoveryDelay(stored));
      } catch {
        setStartupRecoveryDelayMs(DEFAULT_STARTUP_RECOVERY_DELAY_MS);
      }
    })();
  }, []);

  const updateStartupRecoveryDelay = useCallback(async (nextDelayMs: number) => {
    const normalized = normalizeStartupRecoveryDelay(nextDelayMs);
    setStartupRecoveryDelayMs(normalized);
    try {
      await AsyncStorage.setItem(STARTUP_RECOVERY_DELAY_KEY, String(normalized));
      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.localStorage.setItem(STARTUP_RECOVERY_DELAY_KEY, String(normalized));
        window.dispatchEvent(new CustomEvent('startup-recovery-delay-changed', { detail: { delayMs: normalized } }));
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web' || typeof window === 'undefined') return;

    const syncSearch = () => setUrlSearch(window.location.search || '');
    syncSearch();
    window.addEventListener('popstate', syncSearch);
    window.addEventListener('hashchange', syncSearch);
    return () => {
      window.removeEventListener('popstate', syncSearch);
      window.removeEventListener('hashchange', syncSearch);
    };
  }, []);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    try {
      const params = new URLSearchParams(urlSearch || '');
      const categoryParam = (params.get('category') || '').trim();
      const tabParam = (params.get('tab') || '').trim();
      const normalizedTabParam = normalizeOperationsTabId(tabParam);
      if (tabParam && normalizedTabParam && tabParam !== normalizedTabParam) {
        emitAliasTelemetry(tabParam, normalizedTabParam, 'route_param');
      }

      let nextCategory = activeCategory;
      let nextTab = activeTab;

      if (normalizedTabParam) {
        const tabCategory = resolveCategoryForTab(normalizedTabParam);
        if (tabCategory) {
          nextCategory = tabCategory;
          nextTab = normalizedTabParam;
        }
      }

      if (categoryParam) {
        const matchedCategory = CATEGORIES.find((cat) => cat.id === categoryParam);
        const tabCategory = normalizedTabParam ? resolveCategoryForTab(normalizedTabParam) : null;
        if (matchedCategory && (!tabCategory || matchedCategory.id === tabCategory)) {
          nextCategory = matchedCategory.id;
          // Preserve direct-render legacy tabs even if not in CATEGORIES.tabs
          const isDirectRenderTab = DIRECT_RENDER_LEGACY_TABS.has(nextTab);
          if (!isDirectRenderTab && !matchedCategory.tabs.some((tab) => tab.id === nextTab)) {
            nextTab = matchedCategory.tabs[0]?.id || nextTab;
          }
        }
      }

      if (nextCategory !== activeCategory) setActiveCategory(nextCategory);
      if (nextTab !== activeTab) setActiveTab(nextTab);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSearch, resolveCategoryForTab, emitAliasTelemetry]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    try {
      const params = new URLSearchParams(window.location.search);
      params.set('category', activeCategory);
      params.set('tab', activeTab);
      const next = `${window.location.pathname}?${params.toString()}`;
      if (window.location.search !== `?${params.toString()}`) {
        window.history.replaceState({}, '', next);
      }
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch4', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [activeCategory, activeTab]);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let idleHandle: any = null;
    setPanelReady(false);
    const ready = () => setPanelReady(true);
    if (Platform.OS === 'web' && typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      idleHandle = (window as any).requestIdleCallback(ready, { timeout: 900 });
    } else {
      timeoutId = setTimeout(ready, 500);
    }
    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      if (idleHandle && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        (window as any).cancelIdleCallback(idleHandle);
      }
    };
  }, [activeTab]);

  const togglePin = useCallback((tabId: string) => {
    setPinnedTabs(prev => {
      const next = prev.includes(tabId) ? prev.filter(t => t !== tabId) : [...prev, tabId].slice(0, 10);
      AsyncStorage.setItem('admin_console_pinned_tabs', JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  // Keyboard shortcut: Ctrl+K / Cmd+K
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdOpen(prev => !prev);
      }
      if (e.key === 'Escape' && cmdOpen) { closeCmd(); }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [cmdOpen, closeCmd]);

  // Toast alerts from WebSocket
  const [toasts, setToasts] = useState<any[]>([]);

  const refreshAdminConsoleNotifications = useCallback(async () => {
    if (!hasAdminAccess) return;
    try {
      const res = await api.get('/admin/notifications/live?limit=12', { silentLoading: true });
      setLiveNotifications(res.data.notifications || []);
      setNotifCounts(res.data.counts || { total: 0 });
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch5', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    setAdminLastUpdated(new Date());
  }, [hasAdminAccess]);

  const duplicationSeverityColor = useCallback((severity: DuplicationDriftSeverity | string | undefined) => {
    switch (severity) {
      case 'critical': return colors.error;
      case 'high': return colors.error;
      case 'medium': return colors.warning;
      case 'low': return colors.primary;
      default: return colors.successText;
    }
  }, [colors]);

  const refreshDuplicationDrift = useCallback(async () => {
    if (!hasAdminAccess) return;
    setDuplicationDriftLoading(true);
    try {
      const res = await api.get('/admin/autonomous-engine/duplication-drift/status', { silentLoading: true });
      setDuplicationDrift((res?.data || null) as DuplicationDriftResponse | null);
    } catch {
      setDuplicationDrift(null);
    } finally {
      setDuplicationDriftLoading(false);
    }
  }, [hasAdminAccess]);

  const acknowledgeDuplicationDrift = useCallback(async () => {
    if (!hasAdminAccess || duplicationDriftAckLoading) return;
    setDuplicationDriftAckLoading(true);
    try {
      await api.post('/admin/autonomous-engine/duplication-drift/acknowledge', {
        note: 'Acknowledged from Operations Console drift widget',
      });
      await refreshDuplicationDrift();
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch6', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally {
      setDuplicationDriftAckLoading(false);
    }
  }, [duplicationDriftAckLoading, hasAdminAccess, refreshDuplicationDrift]);

  // Push notification alerts — periodic polling of /alerts endpoint
  useEffect(() => {
    if (!hasAdminAccess) return;
    let cancelled = false;
    const pollAlerts = async () => {
      try {
        const res = await api.get('/admin/live-activity/alerts');
        const alerts = res.data?.alerts || [];
        if (!cancelled && alerts.length > 0) {
          const newToasts = alerts.map((a: any) => ({
            id: Date.now() + Math.random(),
            severity: a.level,
            alert_type: a.type,
            title: a.type.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
            message: a.message,
          }));
          setToasts(prev => [...newToasts, ...prev].slice(0, 5));
          // Auto-dismiss after 10s
          newToasts.forEach((t: any) => {
            setTimeout(() => setToasts(prev => prev.filter(p => p.id !== t.id)), 10000);
          });
        }
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/OperationsConsoleView.tsx#catch7', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    };
    // Initial check after 5s, then every 60s
    const initialTimeout = setTimeout(pollAlerts, 5000);
    const interval = setInterval(pollAlerts, 60000);
    return () => { cancelled = true; clearTimeout(initialTimeout); clearInterval(interval); };
  }, [hasAdminAccess]);

  useEffect(() => {
    if (!hasAdminAccess) return;
    refreshAdminConsoleNotifications();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
      refreshAdminConsoleNotifications();
    }, 90000);
    // Also refresh when tab becomes visible
    const onVisible = () => { if (document.visibilityState === 'visible') refreshAdminConsoleNotifications(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVisible); };
  }, [hasAdminAccess, refreshAdminConsoleNotifications]);

  useEffect(() => {
    if (!hasAdminAccess) return;
    refreshDuplicationDrift();
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
      refreshDuplicationDrift();
    }, 120000);
    return () => clearInterval(interval);
  }, [hasAdminAccess, refreshDuplicationDrift]);

  useEffect(() => {
    if (!hasAdminAccess) return;
    const unsubAdminAlert = subscribeType('admin_alert', (data: any) => {
      const toast = { ...data, id: Date.now() + Math.random() };
      setToasts(prev => [toast, ...prev].slice(0, 5));
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== toast.id)), 8000);
      refreshAdminConsoleNotifications();
    });
    const unsubNotification = subscribeType('notification', () => refreshAdminConsoleNotifications());
    const unsubSubscription = subscribeType('subscription_update', () => refreshAdminConsoleNotifications());
    return () => {
      unsubAdminAlert();
      unsubNotification();
      unsubSubscription();
    };
  }, [hasAdminAccess, refreshAdminConsoleNotifications, subscribeType]);

  const scrollRef = React.useRef<ScrollView>(null);
  const duplicationOverall = duplicationDrift?.overall;
  const duplicationRate = Number(duplicationOverall?.combined_drift_rate_pct || 0);
  const duplicationSeverity = (duplicationOverall?.severity || 'none') as DuplicationDriftSeverity;
  const duplicationImpacted = duplicationDrift?.impacted_records || [];
  const duplicationAcknowledgedAt = duplicationDrift?.last_acknowledged?.acknowledged_at
    ? new Date(duplicationDrift.last_acknowledged.acknowledged_at).toLocaleString()
    : null;

  const openAdminTab = useCallback((categoryId: string, tabId: string) => {
    const normalizedTabId = normalizeOperationsTabId(tabId);
    const resolvedCategory = CATEGORIES.find((cat) => cat.id === categoryId)?.id
      || resolveCategoryForTab(normalizedTabId)
      || activeCategory;
    if (tabId !== normalizedTabId) {
      emitAliasTelemetry(tabId, normalizedTabId, 'open_admin_tab');
    }
    setActiveCategory(resolvedCategory);
    setActiveTab(normalizedTabId);
    scrollRef.current?.scrollTo?.({ y: 0, animated: true });
  }, [activeCategory, resolveCategoryForTab, emitAliasTelemetry]);

  const handleCategoryPress = (catId: string) => {
    setActiveCategory(catId);
    const cat = CATEGORIES.find(c => c.id === catId);
    if (cat && cat.tabs.length > 0) {
      setActiveTab(cat.tabs[0].id);
    }
    scrollRef.current?.scrollTo?.({ y: 0, animated: true });
  };

  const activeCat = CATEGORIES.find(c => c.id === activeCategory); // used by selectItem
  const showConsoleRail = width >= 768;
  if (loading) {
    return (
      <AppShell notificationScope="admin">
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="admin-console-auth-loading" testID="admin-console-auth-loading">
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={{ color: colors.textMuted, textAlign: 'center', marginTop: 10, fontSize: 13 }}>{tx('operationsConsole.states.checkingAccess', 'Checking admin access...')}</Text>
        </View>
      </AppShell>
    );
  }

  if (!hasAdminAccess && hasSessionTokenHint && !user) {
    return (
      <AppShell>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="admin-console-session-recovery-loading" testID="admin-console-session-recovery-loading">
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={{ color: colors.textMuted, textAlign: 'center', marginTop: 10, fontSize: 13 }}>{tx('operationsConsole.states.recoveringSession', 'Recovering admin session...')}</Text>
        </View>
      </AppShell>
    );
  }

  if (!hasAdminAccess) {
    return (
      <AppShell>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24 }} data-testid="admin-console-unauthorized" testID="admin-console-unauthorized">
          <Ionicons name="lock-closed" size={40} color={colors.error} />
          <Text style={{ color: colors.text, fontSize: 18, fontWeight: '700', marginTop: 12 }}>{tx('operationsConsole.states.accessDeniedTitle', 'Access Denied')}</Text>
          <Text style={{ color: colors.textMuted, textAlign: 'center', marginTop: 6, fontSize: 13 }}>{tx('operationsConsole.states.accessDeniedSubtitle', 'Admin Console is restricted to authorized administrators.')}</Text>
        </View>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: width < 600 ? 12 : width < 768 ? 14 : width < 1024 ? 18 : 24, paddingBottom: 120, backgroundColor: colors.bg }}
        data-testid="admin-console-page" testID="admin-console-page"
        removeClippedSubviews={false}
      >
        {/* Header */}
        <View style={{ flexDirection: width < 600 ? 'column' : 'row', alignItems: width < 600 ? 'flex-start' : 'center', justifyContent: 'space-between', marginBottom: 20, gap: width < 600 ? 12 : 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
            <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: `${colors.primary}15`, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="settings" size={22} color={colors.primary} />
            </View>
            <View>
              <Text style={{ color: colors.text, fontSize: width < 600 ? 18 : 22, fontWeight: '800', letterSpacing: -0.5 }} data-testid="admin-console-title" testID="admin-console-title">{operationsTitle === 'operationsConsole.header.title' ? 'Operations Console' : operationsTitle}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 2 }}>
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('operationsConsole.header.subtitle', 'Tools, analytics & operational management')}</Text>
                <DataFreshnessIndicator lastUpdated={adminLastUpdated} accentColor={colors.primary} textColor={colors.textMuted} />
              </View>
            </View>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: width < 600 ? 4 : 8, alignSelf: width < 600 ? 'flex-end' : undefined, flexWrap: 'wrap' }}>
            <TouchableOpacity
              accessibilityLabel={tx('operationsConsole.header.openEmailTemplatesA11y', 'Open Email Templates')}
              onPress={() => openAdminTab('comms', 'email-templates')}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                height: width < 600 ? 34 : 38, paddingHorizontal: width < 600 ? 10 : 14, borderRadius: 10,
                backgroundColor: `${colors.primary}12`, borderWidth: 1, borderColor: `${colors.primary}24`,
              }}
              data-testid="admin-console-open-email-templates-button" testID="admin-console-open-email-templates-button"
            >
              <Ionicons name="mail" size={14} color={colors.primary} />
              <Text style={{ color: colors.primary, fontSize: 12, fontWeight: '800' }}>{tx('operationsConsole.header.emailTemplates', 'Email Templates')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              accessibilityLabel={tx('operationsConsole.header.openEmailReliabilityA11y', 'Open Email Reliability')}
              onPress={() => openAdminTab('comms', 'email-reliability')}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                height: width < 600 ? 34 : 38, paddingHorizontal: width < 600 ? 10 : 14, borderRadius: 10,
                backgroundColor: `${colors.success}12`, borderWidth: 1, borderColor: `${colors.success}24`,
              }}
              data-testid="admin-console-open-email-reliability-button" testID="admin-console-open-email-reliability-button"
            >
              <Ionicons name="pulse" size={14} color={colors.success} />
              <Text style={{ color: colors.success, fontSize: 12, fontWeight: '800' }}>{tx('operationsConsole.header.emailReliability', 'Email Reliability')}</Text>
            </TouchableOpacity>
            {/* Executive Dashboard cross-link */}
            <TouchableOpacity accessibilityLabel={tx('operationsConsole.header.goToExecutiveDashboardA11y', 'Go to Executive Dashboard')}
              onPress={() => router.push('/executive-dashboard' as any)}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                height: width < 600 ? 34 : 38, paddingHorizontal: width < 600 ? 10 : 14, borderRadius: 10,
                backgroundColor: 'rgba(16,185,129,0.08)', borderWidth: 1, borderColor: 'rgba(16,185,129,0.20)',
              }}
              data-testid="admin-exec-dashboard-link" testID="admin-exec-dashboard-link"
            >
              <Ionicons name="stats-chart" size={14} color={colors.successText} />
              {width >= 600 && <Text style={{ color: colors.successText, fontSize: 12, fontWeight: '700' }}>{tx('operationsConsole.header.executiveDashboard', 'Executive Dashboard')}</Text>}
              <Ionicons name="open-outline" size={11} color={colors.successText} />
            </TouchableOpacity>
            {/* Command Palette trigger */}
            <TouchableOpacity accessibilityLabel={tx('operationsConsole.header.commandPaletteA11y', 'Open command palette')}
              onPress={openCmd}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 6,
                height: width < 600 ? 34 : 38, paddingHorizontal: width < 600 ? 10 : 12, borderRadius: 10,
                backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border,
              }}
              data-testid="cmd-palette-trigger" testID="cmd-palette-trigger"
            >
              <Ionicons name="search" size={14} color={colors.textMuted} />
              {width >= 600 && <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tx('operationsConsole.header.search', 'Search...')}</Text>}
              {Platform.OS === 'web' && width >= 768 && (
                <View style={{ backgroundColor: colors.bg, paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, borderWidth: 1, borderColor: colors.border, marginLeft: 4 }}>
                  <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '600' }}>{tx('operationsConsole.header.shortcut', 'Ctrl+K')}</Text>
                </View>
              )}
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setThemeMode(darkMode ? 'light' : 'dark')}
              style={{ width: width < 600 ? 34 : 38, height: width < 600 ? 34 : 38, borderRadius: 10, backgroundColor: colors.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border }}
              data-testid="admin-theme-toggle" testID="admin-theme-toggle"
            >
              <Ionicons name={darkMode ? 'sunny' : 'moon'} size={16} color={darkMode ? colors.warning : colors.indigo} />
            </TouchableOpacity>
            <TouchableOpacity accessibilityLabel="Operations debug advanced toggle button"
              onPress={() => setDebugAdvancedMode((prev) => !prev)}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                gap: 6,
                height: width < 600 ? 34 : 38,
                paddingHorizontal: width < 600 ? 10 : 12,
                borderRadius: 10,
                backgroundColor: debugAdvancedMode ? `${colors.warning}1A` : colors.card,
                borderWidth: 1,
                borderColor: debugAdvancedMode ? colors.warning : colors.border,
              }}
              data-testid="operations-debug-advanced-toggle"
              testID="operations-debug-advanced-toggle"
            >
              <Ionicons name={debugAdvancedMode ? 'bug' : 'bug-outline'} size={14} color={debugAdvancedMode ? colors.warning : colors.textMuted} />
              {width >= 600 && (
                <Text style={{ color: debugAdvancedMode ? colors.warning : colors.textMuted, fontSize: 11, fontWeight: '800' }}>
                  {tx('operationsConsole.header.debugAdvanced', 'Debug / Advanced')}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </View>

        <View
          style={{
            marginBottom: 12,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: colors.border,
            backgroundColor: colors.card,
            padding: 12,
            gap: 8,
          }}
          data-testid="operations-enterprise-pulse"
          testID="operations-enterprise-pulse"
        >
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="operations-enterprise-pulse-title" testID="operations-enterprise-pulse-title">
              Operations Enterprise Pulse
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 10 }} data-testid="operations-enterprise-pulse-subtitle" testID="operations-enterprise-pulse-subtitle">
              Category + panel readiness snapshot
            </Text>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {[
              { key: 'categories', label: 'Categories', value: String(CATEGORIES.length), tone: colors.primary },
              { key: 'active-tabs', label: 'Active Category Tabs', value: String(activeCat?.tabs?.length || 0), tone: colors.successText },
              { key: 'pinned', label: 'Pinned', value: String(pinnedTabs.length), tone: colors.warning },
              { key: 'alerts', label: 'Live Alerts', value: String(notifCounts.total || 0), tone: colors.error },
            ].map((metric) => (
              <View
                key={metric.key}
                style={{
                  minWidth: width < 600 ? '47%' : 170,
                  flexGrow: 1,
                  borderRadius: 10,
                  borderWidth: 1,
                  borderColor: colors.border,
                  backgroundColor: colors.bg,
                  padding: 10,
                }}
                data-testid={`operations-enterprise-pulse-${metric.key}`}
                testID={`operations-enterprise-pulse-${metric.key}`}
              >
                <Text style={{ color: colors.textMuted, fontSize: 10 }}>{metric.label}</Text>
                <Text style={{ color: metric.tone, fontSize: 14, fontWeight: '900', marginTop: 4 }}>{metric.value}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Category bar + Sub tabs — MOVED TO TOP for discoverability */}
        {!navCollapsed && (
          <View style={{ marginBottom: 12 }}>
            <OperationsCategoryBar
              activeCategory={activeCategory}
              onCategoryPress={handleCategoryPress}
              activeTab={canonicalActiveTab}
              onTabPress={setActiveTab}
              colors={colors}
              width={width}
              showDebugAdvanced={debugAdvancedMode}
            />
          </View>
        )}

        {/* Overview quick actions + summaries — only visible on Overview category */}
        {activeCategory === 'overview' && (
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap', marginBottom: 12 }} data-testid="admin-console-overview-cards" testID="admin-console-overview-cards">
          <TouchableOpacity
            onPress={() => openAdminTab('operations', 'enterprise-control-plane')}
            style={{ backgroundColor: darkMode ? (colors.surfaceElevated || colors.card) : colors.card, borderWidth: 1, borderColor: colors.primary, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, minWidth: 180 }}
            data-testid="admin-console-open-enterprise-control-plane" testID="admin-console-open-enterprise-control-plane"
          >
            <Text style={{ color: colors.primary, fontSize: 11, fontWeight: '700' }}>{tx('operationsConsole.overview.priorityAccess', 'Priority Access')}</Text>
            <Text style={{ color: colors.text, fontSize: 15, fontWeight: '800', marginTop: 4 }}>{tx('operationsConsole.overview.enterpriseControlPlane', 'Enterprise Control Plane')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }}>{tx('operationsConsole.overview.enterpriseControlPlaneSubtitle', 'Open SLO auto-mitigation and runbook controls directly.')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/executive-dashboard?section=notifications' as any)} style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, minWidth: 140 }} data-testid="admin-console-summary-notifications" testID="admin-console-summary-notifications">
            <Text style={{ color: colors.warningText, fontSize: 18, fontWeight: '800' }}>{notifCounts.total || 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('operationsConsole.overview.liveAlerts', 'Live Alerts')}</Text>
          </TouchableOpacity>
          <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, minWidth: 140 }} data-testid="admin-console-summary-pinned-tabs" testID="admin-console-summary-pinned-tabs">
            <Text style={{ color: colors.primary, fontSize: 18, fontWeight: '800' }}>{pinnedTabs.length}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('operationsConsole.overview.pinnedTabs', 'Pinned Tabs')}</Text>
          </View>
          <View style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, minWidth: 140 }} data-testid="admin-console-summary-active-category-tabs" testID="admin-console-summary-active-category-tabs">
            <Text style={{ color: colors.successText, fontSize: 18, fontWeight: '800' }}>{activeCat?.tabs?.length || 0}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '600' }}>{tx('operationsConsole.overview.categoryModules', 'Category Modules')}</Text>
          </View>
          <View
            style={{
              backgroundColor: colors.card,
              borderWidth: 1,
              borderColor: duplicationSeverityColor(duplicationSeverity),
              borderRadius: 12,
              paddingHorizontal: 12,
              paddingVertical: 10,
              minWidth: 290,
              flexGrow: 1,
            }}
            data-testid="operations-duplication-drift-card"
            testID="operations-duplication-drift-card"
          >
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <Text style={{ color: colors.text, fontSize: 12, fontWeight: '800' }} data-testid="operations-duplication-drift-title" testID="operations-duplication-drift-title">
                Duplication Drift Detector
              </Text>
              <View style={{ backgroundColor: `${duplicationSeverityColor(duplicationSeverity)}1A`, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 4 }} data-testid="operations-duplication-drift-severity" testID="operations-duplication-drift-severity">
                <Text style={{ color: duplicationSeverityColor(duplicationSeverity), fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>
                  {duplicationSeverity}
                </Text>
              </View>
            </View>

            <Text style={{ color: duplicationSeverityColor(duplicationSeverity), fontSize: 20, fontWeight: '900', marginTop: 6 }} data-testid="operations-duplication-drift-rate" testID="operations-duplication-drift-rate">
              {duplicationDriftLoading ? 'Loading…' : `${duplicationRate.toFixed(2)}%`}
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 2 }} data-testid="operations-duplication-drift-summary" testID="operations-duplication-drift-summary">
              {(duplicationOverall?.exact_duplicate_records || 0)} exact · {(duplicationOverall?.near_duplicate_records || 0)} near · {(duplicationOverall?.total_records_scanned || 0)} scanned
            </Text>

            <Text style={{ color: colors.textMuted, fontSize: 10, marginTop: 5 }} data-testid="operations-duplication-drift-last-ack" testID="operations-duplication-drift-last-ack">
              {duplicationAcknowledgedAt
                ? `Last acknowledged ${duplicationAcknowledgedAt}`
                : 'No acknowledgement logged yet'}
            </Text>

            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 9 }}>
              <TouchableOpacity
                onPress={() => setDuplicationDriftExpanded((prev) => !prev)}
                style={{ borderRadius: 9, borderWidth: 1, borderColor: colors.border, paddingHorizontal: 10, paddingVertical: 7, backgroundColor: colors.bg }}
                data-testid="operations-duplication-drift-view-records-button"
                testID="operations-duplication-drift-view-records-button"
              >
                <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }}>
                  {duplicationDriftExpanded ? 'Hide impacted records' : `View impacted records (${duplicationImpacted.length})`}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={acknowledgeDuplicationDrift}
                style={{ borderRadius: 9, borderWidth: 1, borderColor: duplicationSeverityColor(duplicationSeverity), paddingHorizontal: 10, paddingVertical: 7, backgroundColor: `${duplicationSeverityColor(duplicationSeverity)}12` }}
                data-testid="operations-duplication-drift-acknowledge-button"
                testID="operations-duplication-drift-acknowledge-button"
              >
                <Text style={{ color: duplicationSeverityColor(duplicationSeverity), fontSize: 11, fontWeight: '800' }} data-testid="operations-duplication-drift-acknowledge-button-label" testID="operations-duplication-drift-acknowledge-button-label">
                  {duplicationDriftAckLoading ? 'Acknowledging…' : 'Acknowledge'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
        )}

        {activeCategory === 'overview' && duplicationDriftExpanded && (
          <View style={{ marginBottom: 12, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 12 }} data-testid="operations-duplication-drift-impacted-panel" testID="operations-duplication-drift-impacted-panel">
            <Text style={{ color: colors.text, fontSize: 13, fontWeight: '800' }} data-testid="operations-duplication-drift-impacted-title" testID="operations-duplication-drift-impacted-title">
              Impacted Records (Top {Math.min(duplicationImpacted.length, 10)})
            </Text>
            <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4, marginBottom: 8 }} data-testid="operations-duplication-drift-impacted-subtitle" testID="operations-duplication-drift-impacted-subtitle">
              Near-duplicates are computed using relaxed fingerprints to catch structurally similar repeated events.
            </Text>

            {duplicationImpacted.length === 0 ? (
              <View style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, padding: 10, backgroundColor: colors.bg }} data-testid="operations-duplication-drift-impacted-empty" testID="operations-duplication-drift-impacted-empty">
                <Text style={{ color: colors.textMuted, fontSize: 11 }}>No impacted records detected in current scan window.</Text>
              </View>
            ) : (
              <View style={{ gap: 8 }} data-testid="operations-duplication-drift-impacted-list" testID="operations-duplication-drift-impacted-list">
                {duplicationImpacted.slice(0, 10).map((item, index) => (
                  <View
                    key={`${item.dataset}-${item.mode}-${index}`}
                    style={{ borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.bg, padding: 10 }}
                    data-testid={`operations-duplication-drift-impacted-item-${index}`}
                    testID={`operations-duplication-drift-impacted-item-${index}`}
                  >
                    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                      <Text style={{ color: colors.text, fontSize: 11, fontWeight: '800' }} data-testid={`operations-duplication-drift-impacted-item-dataset-${index}`} testID={`operations-duplication-drift-impacted-item-dataset-${index}`}>
                        {item.label}
                      </Text>
                      <Text style={{ color: item.mode === 'exact' ? colors.error : colors.warning, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }} data-testid={`operations-duplication-drift-impacted-item-mode-${index}`} testID={`operations-duplication-drift-impacted-item-mode-${index}`}>
                        {item.mode}
                      </Text>
                    </View>
                    <Text style={{ color: colors.textMuted, fontSize: 11, marginTop: 4 }} data-testid={`operations-duplication-drift-impacted-item-occurrences-${index}`} testID={`operations-duplication-drift-impacted-item-occurrences-${index}`}>
                      {item.occurrences} occurrences · sample IDs: {(item.sample_ids || []).join(', ') || 'n/a'}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {activeCategory === 'overview' && (
          <GlobalParityAuditCard
            colors={colors}
            onNavigateToIncidentBoard={() => openAdminTab('security', 'security-incidents')}
          />
        )}

        {activeCategory === 'overview' && (
          <View style={{ marginTop: 12, marginBottom: 12 }} data-testid="entitlement-drift-card-wrap" testID="entitlement-drift-card-wrap">
            <EntitlementDriftAuditCard
              colors={colors}
              onNavigate={() => openAdminTab('platform', 'entitlement-drift-audit')}
            />
          </View>
        )}

        {/* Theme Compliance Dashboard Widgets — only on Overview */}
        {activeCategory === 'overview' && (
        <View style={{ flexDirection: width < 720 ? 'column' : 'row', gap: 12, marginBottom: 12 }}>
          <ThemeComplianceWidget />
          <V7TemplateComplianceWidget />
        </View>
        )}

        {/* Top Theme Offenders Leaderboard — only on Overview */}
        {activeCategory === 'overview' && (
        <View style={{ marginBottom: 12 }}>
          <TopThemeOffendersLeaderboard />
        </View>
        )}

        {activeCategory === 'overview' && (
          <View style={{ marginBottom: 12 }} data-testid="sports-conversion-card-wrap" testID="sports-conversion-card-wrap">
            <SportsConversionCard colors={colors} />
          </View>
        )}

        {/* Breadcrumb + navigation controls */}
        <View style={{ flexDirection: width < 720 ? 'column' : 'row', alignItems: width < 720 ? 'flex-start' : 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
          <Text style={{ color: colors.textMuted, fontSize: 12 }} data-testid="admin-console-breadcrumb" testID="admin-console-breadcrumb">
            {tx('operationsConsole.header.title', 'Operations Console')} / {activeCat?.label || tx('operationsConsole.breadcrumb.overview', 'Overview')} / {activeItem?.label || tx('operationsConsole.breadcrumb.panel', 'Panel')}
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 9, paddingHorizontal: 8, paddingVertical: 6 }} data-testid="startup-recovery-delay-control" testID="startup-recovery-delay-control">
              <Text style={{ color: colors.textMuted, fontSize: 10, fontWeight: '700' }} data-testid="startup-recovery-delay-label" testID="startup-recovery-delay-label">Recovery auto-refresh</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                {STARTUP_RECOVERY_DELAY_OPTIONS.map((delayMs) => {
                  const active = startupRecoveryDelayMs === delayMs;
                  return (
                    <TouchableOpacity accessibilityLabel="Update startup recovery delay in operations console view button"
                      key={delayMs}
                      onPress={() => updateStartupRecoveryDelay(delayMs)}
                      style={{
                        borderRadius: 999,
                        paddingHorizontal: 8,
                        paddingVertical: 4,
                        borderWidth: 1,
                        borderColor: active ? colors.primary : colors.border,
                        backgroundColor: active ? `${colors.primary}1A` : colors.bg,
                      }}
                      data-testid={`startup-recovery-delay-option-${delayMs}`}
                      testID={`startup-recovery-delay-option-${delayMs}`}
                    >
                      <Text style={{ color: active ? colors.primary : colors.textMuted, fontSize: 10, fontWeight: '800' }}>{Math.round(delayMs / 1000)}s</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
            <TouchableOpacity
              onPress={() => setNavCollapsed(v => !v)}
              style={{ backgroundColor: colors.card, borderWidth: 1, borderColor: colors.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5 }}
              data-testid="admin-console-nav-collapse-toggle" testID="admin-console-nav-collapse-toggle"
            >
              <Ionicons name={navCollapsed ? 'chevron-down' : 'chevron-up'} size={13} color={colors.textMuted} />
              <Text style={{ color: colors.textMuted, fontSize: 11, fontWeight: '700' }}>{navCollapsed ? tx('operationsConsole.navigation.expandNav', 'Expand Nav') : tx('operationsConsole.navigation.collapseNav', 'Collapse Nav')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => togglePin(canonicalActiveTab)}
              style={{ backgroundColor: pinnedTabs.includes(canonicalActiveTab) ? colors.warningSoft : colors.card, borderWidth: 1, borderColor: pinnedTabs.includes(canonicalActiveTab) ? colors.warningSoft : colors.border, borderRadius: 9, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5 }}
              data-testid="admin-console-pin-active-tab" testID="admin-console-pin-active-tab"
            >
              <Ionicons name={pinnedTabs.includes(canonicalActiveTab) ? 'star' : 'star-outline'} size={13} color={pinnedTabs.includes(canonicalActiveTab) ? colors.warning : colors.textMuted} />
              <Text style={{ color: pinnedTabs.includes(canonicalActiveTab) ? colors.warning : colors.textMuted, fontSize: 11, fontWeight: '700' }}>
                {pinnedTabs.includes(canonicalActiveTab) ? tx('operationsConsole.navigation.pinned', 'Pinned') : tx('operationsConsole.navigation.pinTab', 'Pin Tab')}
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Pinned tabs */}
        {pinnedItems.length > 0 && (
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 12 }} data-testid="admin-console-pinned-tabs-row" testID="admin-console-pinned-tabs-row">
            {pinnedItems.map((item) => (
              <TouchableOpacity
                key={`pinned-${item.id}`}
                onPress={() => { setActiveCategory(item.catId); setActiveTab(item.id); }}
                style={{ backgroundColor: colors.warningSoft, borderWidth: 1, borderColor: colors.warningSoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6, flexDirection: 'row', alignItems: 'center', gap: 5 }}
                data-testid={`admin-console-pinned-tab-${item.id}`} testID={`admin-console-pinned-tab-${item.id}`}
              >
                <Ionicons name={item.icon as any} size={12} color={colors.warningText} />
                <Text style={{ color: colors.warningText, fontSize: 11, fontWeight: '700' }}>{item.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Category bar + Sub tabs */}
        {!navCollapsed && null /* moved above for discoverability */ }

        {/* Panel content */}
        {panelReady ? (
          <ErrorBoundary
            key={activeTab}
            panelId={activeTab}
            panelName={activeItem?.label || activeTab}
          >
            <>
              {(activeTab === 'dashboard' || canonicalActiveTab === 'ops-command-center' || activeCategory === 'overview') && (
                <>
                  <TopBrokenPanelsWidget colors={colors} onNavigate={setActiveTab} />
                  <View style={{ height: 12 }} />
                  <AdminHealthDigestWidget colors={colors} />
                  <PreviewFreshnessCard colors={colors} />
                  <PreviewBrowserE2ECard colors={colors} />
                  <AudioStudioConversionCard colors={colors} />
                  <PodcastsConversionCard colors={colors} />
                </>
              )}
              <PanelContent tabId={activeTab} colors={colors} darkMode={darkMode} onNavigate={setActiveTab} />
            </>
          </ErrorBoundary>
        ) : (
          <View style={{ borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.card, padding: 18, minHeight: 240, justifyContent: 'center', alignItems: 'center' }} data-testid="admin-console-panel-loading-state" testID="admin-console-panel-loading-state">
            <ActivityIndicator size="small" color={colors.primary} />
            <Text style={{ color: colors.text, fontSize: 14, fontWeight: '700', marginTop: 12 }}>{tx('operationsConsole.panelLoading.title', 'Loading module')}</Text>
            <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 6, textAlign: 'center', maxWidth: 320 }}>
              {tx('operationsConsole.panelLoading.subtitle', 'Prioritizing console chrome and navigation first, then warming the selected panel.')}
            </Text>
          </View>
        )}

        {/* Admin footer — live GTEC compliance score */}
        <GtecComplianceBadge />
      </ScrollView>

      <SectionProgressRail
        visible={showConsoleRail}
        colors={colors}
        railTestId="operations-progress-rail"
        activeId={activeCategory}
        onSelect={handleCategoryPress}
        top={130}
        right={12}
        maxWidth={170}
        items={CATEGORIES.map((cat) => ({ id: cat.id, label: cat.label }))}
      />

      {/* Toast alerts */}
      <OperationsToastAlerts toasts={toasts} onDismiss={(id) => setToasts(prev => prev.filter(t => t.id !== id))} />

      {/* Command Palette Modal */}
      <OperationsCommandPalette
        open={cmdOpen}
        onClose={closeCmd}
        onSelect={(item) => { setActiveCategory(item.catId); setActiveTab(item.id); closeCmd(); }}
        onSelectExec={(tabId) => { closeCmd(); router.push((`/executive-dashboard?tab=${tabId}`) as any); }}
        colors={colors}
      />
    </AppShell>
  );
}

