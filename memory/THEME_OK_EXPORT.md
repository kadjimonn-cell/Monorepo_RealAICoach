## Theme-OK Annotations Audit

_Generated 2026-04-21 01:41 UTC · 168 file-level pragmas · 223 inline annotations_

Every intentional deviation from the V2 Teal theme system is annotated with a `@theme-ok` / `@theme-audit-file-ok` pragma. This report makes those exceptions easy to review in PRs.

### File-level pragmas (always-dark ops panels, etc.)

| File | Reason |
| --- | --- |
| `app/+html.tsx` | root HTML template — dark hex literals are all |
| `app/achievements.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/admin/gdpr-requests.tsx` | GDPR request status chrome (pending/approved/rejected semantic) |
| `app/ai-briefing.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/ai-problem-solver.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/auth/ms-callback.tsx` | Microsoft SSO callback brand/state chrome |
| `app/auth/qr-approve.tsx` | QR-approve cyan gradient (auth brand chrome) |
| `app/blog/[slug].tsx` | blog post syntax-highlighting chrome + tag colors (content-layer, theme-agnostic) |
| `app/blog/index.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/career.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/executive-dashboard.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/feature-gallery.tsx` | marketing gallery uses intentional dark-navy backdrop for contrast |
| `app/feedback.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/id-verify-mobile.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/integrations.tsx` | third-party integration brand logos (Google/PayPal/Swiss/etc.) |
| `app/leaderboard.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/mini-apps/creator-exchange.tsx` | creator exchange purple accent (intentional brand chrome) |
| `app/mini-apps/digital-bank.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/mini-apps/drama-box.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/mini-apps/marketplace.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/mini-apps/mobile-money.tsx` | mobile-money provider brand colors (MTN/Orange/Moov/FedaPay) |
| `app/privacy-security.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/privacy-verify.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/progress-tracker.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/progress.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/safe-deployment.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/settings/payment-cards.tsx` | payment provider brand colors |
| `app/subscription/kyc.tsx` | KYC status badge chrome (pending/rejected semantic) |
| `app/subscription/mobile-money.tsx` | mobile-money provider brand colors |
| `app/subscription/plans.tsx` | payment-method provider brand colors |
| `app/track-application.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `app/verify.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/AIScanner.tsx` | scanner overlay viewfinder chrome (semantic scan states) |
| `src/components/AdminConsoleView.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/AppShell.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/DailyGoalRing.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/DownloadsManagerView.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/MobileSubscriptionsView.tsx` | subscription tier badge colors (semantic) |
| `src/components/OfflineBanner.tsx` | offline/degraded/online banner state colors (semantic state chrome, theme-agnostic) |
| `src/components/OnboardingWizard.tsx` | onboarding persona/category identity colors (semantic) |
| `src/components/PWAInstallBanner.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/SessionExpiryBanner.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/SessionTimeout.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/SubscriptionUpgradeModal.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/TosAcceptanceModal.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/UpgradeBanner.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/UpgradeModal.tsx` | upgrade modal reason pill (warning/error semantic, intentional chrome) |
| `src/components/UsageLimitIndicator.tsx` | usage-limit state indicator (red/green semantic) |
| `src/components/WhiteboardCanvas.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/accessibility/SkipToContent.tsx` | skip-link uses intentional fixed accent for cross-theme visibility |
| `src/components/admin-console/AdminConsoleExtracted.tsx` | admin module category color swatches (semantic category mapping) |
| `src/components/admin/AIAutoSupportPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AIFeatureAnalyticsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AIInsightHelpers.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AIInsightsPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AIPlatformIntegrityPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AIRemediationPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AIUsageAnalyticsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/ASOAnalyticsSection.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AccessibilityPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AdminAnalyticsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AdminNotificationHistoryPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AnomalyDetectionPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AppStoreConnectPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AttachmentLightbox.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AuthComplianceDashboardPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AutoDetectPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AutoScalingPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/AutomationEnginePanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/AutonomousEnginePanel.tsx` | engine action-button semantic color tags (drift=cyan, feedback=amber, forever=violet) |
| `src/components/admin/CIATrustScoreWidget.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/CareerApplicationsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/CertificateAnalyticsPanel.tsx` | chart data-series semantic palette |
| `src/components/admin/CertificateTemplateManagerPanel.tsx` | certificate template preview chrome |
| `src/components/admin/CodeHealthPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/CompetitorSnapshot.tsx` | competitor brand logo chrome (Apple/Google/etc.) |
| `src/components/admin/ConversionAnalyticsPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/CriticalJourneyMonitorPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/CsatDashboardPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/DeploymentOrchestrationPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/DeviceAuditPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/EmailCoverageMatrixPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/EnterpriseControlPlanePanel.tsx` | control-plane action button semantic colors |
| `src/components/admin/EnterpriseSecurityPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/ExecDashboardPanels.tsx` | exec dashboard sidebar uses intentional dark navy chrome |
| `src/components/admin/FeedbackHeatmapPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/FraudDetectionPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/GlobalAdaptationControlCenterPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/GooglePlayPanel.tsx` | Google Play brand identity chrome |
| `src/components/admin/HiringAnalyticsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/IAPManagementPanel.tsx` | IAP provider brand colors + state chrome |
| `src/components/admin/IntegrationManagementPanel.tsx` | third-party integration brand logos (Google/Slack/Stripe/etc.) |
| `src/components/admin/NewsletterAnalyticsPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | analytics chart fill colors (data-series palette) |
| `src/components/admin/OnboardingAnalyticsPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/OperationsDashboard.tsx` | ops status pill semantic colors (navy=staged, amber=queued, etc.) |
| `src/components/admin/PaymentRecoveryPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/PerfAdvisorPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/PerformanceDashboardPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/PlatformAnalyticsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/PlatformFinanceIntegrityPanel.tsx` | IAP audit share-link indigo chrome + provider state tints |
| `src/components/admin/PlatformHealthPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/PlatformSettingsPanel.tsx` | settings category color coding (semantic) |
| `src/components/admin/ReceiptBrandingPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/SIEMPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SLAMonitorPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SSOAnalyticsPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SSOStatusPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SecurityDashboardPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/SecurityPosturePanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SecurityRecommendationsPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/SecurityTrendDashboard.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SelfRepairPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SessionManagementPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SessionReplayPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/SubscriberGrowthPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/SubscriptionAnalyticsPanel.tsx` | subscription tier/state indicator colors |
| `src/components/admin/SubscriptionPlanManagementPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/SystemMonitorPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/ThemeComplianceWidget.tsx` | meta: widget visualizes compliance red-flag UI itself — intentional |
| `src/components/admin/ThemeTokenRemediationPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/ThreatDetectionPanel.tsx` | intentional always-dark ops/admin panel (V2 exception — ops dashboards run dark for operator visibility across lighting conditions) |
| `src/components/admin/TicketFeedbackIntelPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/UnifiedASOPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/UnifiedRevenuePanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/ZeroTrustCenterPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/email-templates/AbTestsView.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/email-templates/AnalyticsView.tsx` | email analytics chart palette |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/email-templates/DeliverabilityView.tsx` | deliverability status chrome |
| `src/components/admin/email-templates/PerformanceChartsView.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/email-templates/TemplatesView.tsx` | web-only preview fallback chrome |
| `src/components/admin/session-management/AlertsPanel.tsx` | session alert status chrome |
| `src/components/admin/session-management/BlocklistPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/session-management/GeoMapPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/admin/session-management/PoliciesPanel.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/agenda/AgendaSidebar.tsx` | calendar event type color coding (semantic) |
| `src/components/agenda/EventDetailModal.tsx` | event category color coding |
| `src/components/agenda/EventFormModal.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/branding/EnterpriseMotionOverlay.tsx` | motion overlay brand identity chrome |
| `src/components/charts/RadarChart.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/executive/ExecInlinePanels.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/executive/ExecOverviewSection.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/executive/ExecSearchModal.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/executive/ExecSidebar.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/AILearningDashboard.tsx` | candidate tier status colors (semantic hiring pipeline) |
| `src/components/hiring/AIMatchTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/CandOverviewTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/CareerCoachTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/FairnessDashboard.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/InterviewPrepTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/InterviewSummary.tsx` | interview outcome status colors |
| `src/components/hiring/PipelineTab.tsx` | pipeline stage color semantics |
| `src/components/hiring/PredictiveTimeline.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/RankingsTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/ResumeBuilderTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/hiring/SchedulerTab.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/notifications/NotificationsWorkspace.tsx` | notification severity color palette (semantic) |
| `src/components/pages/CalendarInner.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/pages/LoginInner.tsx` | last-used-method semantic chip (cyan=Google, indigo=Microsoft) + SSO callback chrome |
| `src/components/pages/PaymentHistoryInner.tsx` | tax badge + invoice status semantic chrome (amber tax, emerald success) |
| `src/components/pages/SettingsInner.tsx` | locale flag/brand swatches + status chrome |
| `src/components/payment/BillingGlossaryTooltip.tsx` | tooltip is intentional dark preview card (chrome is theme-agnostic) |
| `src/components/payment/EnterprisePaymentSummary.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/payment/PdfAnnotationLayer.tsx` | PDF annotation highlight colors (content-layer) |
| `src/components/payment/PdfCanvasPreview.tsx` | residual-semantic-hex — reviewed; lines contain intentional semantic hex (e.g., '#FEFEFE' button text, error/warn brand colors) |
| `src/components/portfolio/LearnerPortfolioScreen.tsx` | portfolio tier badge colors (semantic) |
| `src/components/profile/ProfilePhotoCropper.tsx` | cropper grid overlay — intentional theme-agnostic black/white chrome |

### Inline annotations (grouped by reason)

**admin-always-dark widget** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/admin/CIATrustScoreWidget.tsx` | 13 |

**brand identifier** — 12 occurrences

| File | Line |
| --- | --- |
| `src/components/admin/IntegrationManagementPanel.tsx` | 17 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 18 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 19 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 20 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 22 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 23 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 24 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 25 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 26 |
| `src/components/admin/IntegrationManagementPanel.tsx` | 27 |
| `src/components/admin/SubscriptionAnalyticsPanel.tsx` | 68 |
| `src/components/admin/SubscriptionAnalyticsPanel.tsx` | 182 |

**brand/role/state identifier** — 132 occurrences

| File | Line |
| --- | --- |
| `app/(tabs)/content-library.tsx` | 27 |
| `app/(tabs)/content-library.tsx` | 28 |
| `app/(tabs)/content-library.tsx` | 29 |
| `app/(tabs)/content-library.tsx` | 30 |
| `app/(tabs)/progress.tsx` | 33 |
| `app/auth/forgot-password.tsx` | 21 |
| `app/auth/forgot-password.tsx` | 22 |
| `app/auth/reset-password.tsx` | 21 |
| `app/auth/reset-password.tsx` | 22 |
| `app/blog/[slug].tsx` | 22 |
| `app/blog/[slug].tsx` | 23 |
| `app/blog/index.tsx` | 20 |
| `app/blog/index.tsx` | 21 |
| `app/edit-profile.tsx` | 27 |
| `app/edit-profile.tsx` | 28 |
| `app/features/index.tsx` | 15 |
| `app/features/index.tsx` | 16 |
| `app/features/index.tsx` | 17 |
| `app/features/index.tsx` | 18 |
| `app/features/index.tsx` | 19 |
| `app/features/index.tsx` | 20 |
| `app/leaderboard.tsx` | 20 |
| `app/leaderboard.tsx` | 338 |
| `app/my-analytics.tsx` | 17 |
| `app/my-analytics.tsx` | 18 |
| `app/my-analytics.tsx` | 22 |
| `app/my-analytics.tsx` | 23 |
| `app/privacy-security.tsx` | 29 |
| `app/privacy-security.tsx` | 30 |
| `app/privacy-security.tsx` | 31 |
| `app/session-history.tsx` | 21 |
| `app/session-history.tsx` | 22 |
| `app/session-history.tsx` | 23 |
| `app/session-history.tsx` | 27 |
| `app/session-history.tsx` | 28 |
| `app/session-history.tsx` | 29 |
| `app/session-history.tsx` | 30 |
| `app/session-history.tsx` | 31 |
| `app/session-history.tsx` | 32 |
| `app/subscription/payment.tsx` | 24 |
| `app/subscription/payment.tsx` | 25 |
| `app/subscription/payment.tsx` | 26 |
| `app/subscription/payment.tsx` | 27 |
| `app/subscription/payment.tsx` | 28 |
| `app/subscription/payment.tsx` | 29 |
| `app/track-application.tsx` | 43 |
| `src/components/MockInterviewContent.tsx` | 477 |
| `src/components/admin/AccessMatrixPanel.tsx` | 9 |
| `src/components/admin/AutoFixBanner.tsx` | 20 |
| `src/components/admin/BatchAIPanel.tsx` | 10 |
| `src/components/admin/BatchAIPanel.tsx` | 11 |
| `src/components/admin/BatchAIPanel.tsx` | 12 |
| `src/components/admin/BatchAIPanel.tsx` | 13 |
| `src/components/admin/BatchAIPanel.tsx` | 17 |
| `src/components/admin/BatchAIPanel.tsx` | 18 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 9 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 10 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 11 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 12 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 16 |
| `src/components/admin/CatAnalyticsPanel.tsx` | 17 |
| `src/components/admin/ChurnRecoveryPanel.tsx` | 55 |
| `src/components/admin/ChurnRecoveryPanel.tsx` | 56 |
| `src/components/admin/ChurnRecoveryPanel.tsx` | 57 |
| `src/components/admin/ChurnRecoveryPanel.tsx` | 58 |
| `src/components/admin/ContentStudioAnalyticsPanel.tsx` | 23 |
| `src/components/admin/ContentStudioAnalyticsPanel.tsx` | 27 |
| `src/components/admin/ContentStudioAnalyticsPanel.tsx` | 28 |
| `src/components/admin/EnterpriseControlPlanePanel.tsx` | 11 |
| `src/components/admin/EnterpriseControlPlanePanel.tsx` | 12 |
| `src/components/admin/EnterpriseControlPlanePanel.tsx` | 13 |
| `src/components/admin/EnterpriseControlPlanePanel.tsx` | 14 |
| `src/components/admin/NewsletterAnalyticsPanel.tsx` | 26 |
| `src/components/admin/NewsletterAnalyticsPanel.tsx` | 27 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 21 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 22 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 23 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 24 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 25 |
| `src/components/admin/NewsletterAnalyticsPanelV2.tsx` | 26 |
| `src/components/admin/NotificationRulesPanel.tsx` | 19 |
| `src/components/admin/NotificationRulesPanel.tsx` | 20 |
| `src/components/admin/NotificationRulesPanel.tsx` | 21 |
| `src/components/admin/OnboardingABPanel.tsx` | 9 |
| `src/components/admin/OnboardingABPanel.tsx` | 10 |
| `src/components/admin/OnboardingABPanel.tsx` | 11 |
| `src/components/admin/PromptABTestingPanel.tsx` | 49 |
| `src/components/admin/SIEMPanel.tsx` | 12 |
| `src/components/admin/SSOAnalyticsPanel.tsx` | 20 |
| `src/components/admin/SecurityRecommendationsPanel.tsx` | 24 |
| `src/components/admin/TeamAnalyticsPanel.tsx` | 9 |
| `src/components/admin/TeamAnalyticsPanel.tsx` | 10 |
| `src/components/admin/TeamAnalyticsPanel.tsx` | 11 |
| `src/components/admin/TeamAnalyticsPanel.tsx` | 12 |
| `src/components/admin/TeamAnalyticsPanel.tsx` | 13 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 9 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 10 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 11 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 12 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 13 |
| `src/components/admin/ThemeComplianceWidget.tsx` | 14 |
| `src/components/admin/WebVitalsPanel.tsx` | 23 |
| `src/components/admin/WebVitalsPanel.tsx` | 24 |
| `src/components/admin/WebVitalsPanel.tsx` | 25 |
| `src/components/admin/WebhookEventStreamPanel.tsx` | 10 |
| `src/components/admin/WebhookEventStreamPanel.tsx` | 11 |
| `src/components/admin/WebhookEventStreamPanel.tsx` | 21 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 43 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 44 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 45 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 49 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 50 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 51 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 52 |
| `src/components/admin/email-templates/ClientSandboxView.tsx` | 53 |
| `src/components/admin/session-management/types.ts` | 5 |
| `src/components/admin/session-management/types.ts` | 6 |
| `src/components/admin/session-management/types.ts` | 7 |
| `src/components/admin/session-management/types.ts` | 8 |
| `src/components/admin/session-panels/types.ts` | 5 |
| `src/components/admin/session-panels/types.ts` | 6 |
| `src/components/admin/session-panels/types.ts` | 7 |
| `src/components/admin/session-panels/types.ts` | 8 |
| `src/components/home/HomeChecklist.tsx` | 114 |
| `src/components/home/HomeChecklist.tsx` | 115 |
| `src/components/home/HomeChecklist.tsx` | 116 |
| `src/components/home/HomeChecklist.tsx` | 117 |
| `src/components/home/HomeChecklist.tsx` | 118 |
| `src/components/pages/PaymentHistoryInner.tsx` | 23 |
| `src/components/pages/PaymentHistoryInner.tsx` | 24 |
| `src/components/pages/ReferralsInner.tsx` | 11 |
| `src/components/pages/ReferralsInner.tsx` | 15 |

**button-icon-on-fixed-accent-bg** — 1 occurrence

| File | Line |
| --- | --- |
| `app/+not-found.tsx` | 69 |

**crash-overlay (UIEM watchdog runs on pre-theme error boundary)** — 1 occurrence

| File | Line |
| --- | --- |
| `src/uiem/UIEMWatchdog.tsx` | 76 |

**css-var-fallback (runtime override sets --app-bg from theme)** — 3 occurrences

| File | Line |
| --- | --- |
| `app/_layout.tsx` | 558 |
| `app/_layout.tsx` | 750 |
| `src/components/ErrorBoundary.tsx` | 142 |

**dark-branch** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/SubscriptionBadge.tsx` | 77 |

**dark-text-on-light-card** — 2 occurrences

| File | Line |
| --- | --- |
| `app/chat/[id].tsx` | 31 |
| `app/scenario/[id].tsx` | 25 |

**dep-array-fingerprint (not a rendered color)** — 1 occurrence

| File | Line |
| --- | --- |
| `app/_layout.tsx` | 621 |

**fixed-badge-palette** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/SubscriptionBadge.tsx` | 108 |

**form-input-border-neutral** — 2 occurrences

| File | Line |
| --- | --- |
| `app/careers.tsx` | 50 |
| `app/careers.tsx` | 64 |

**html-export-fixed-palette** — 4 occurrences

| File | Line |
| --- | --- |
| `app/admin-activity-log.tsx` | 141 |
| `app/payment-history-export-v2.tsx` | 179 |
| `app/payment-history-export-v2.tsx` | 188 |
| `src/components/gallery/FeatureDetailModal.tsx` | 130 |

**intentional dark hero backdrop (feature layout cover)** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/FeatureLayout.tsx` | 102 |

**ios-shadow-base** — 1 occurrence

| File | Line |
| --- | --- |
| `app/features/index.tsx` | 353 |

**isDarkTheme-gated** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/FloatingImageShowcase.tsx` | 234 |

**residual semantic hex (reviewed)** — 48 occurrences

| File | Line |
| --- | --- |
| `app/(tabs)/practice.tsx` | 43 |
| `app/(tabs)/progress.tsx` | 29 |
| `app/auth/forgot-password.tsx` | 263 |
| `app/auth/register.tsx` | 430 |
| `app/auth/reset-password.tsx` | 496 |
| `app/book-meeting.tsx` | 337 |
| `app/chat/[id].tsx` | 27 |
| `app/features/ai-automations.tsx` | 69 |
| `app/features/ai-chatbot.tsx` | 67 |
| `app/features/ai-cognitive.tsx` | 69 |
| `app/features/ai-enterprise.tsx` | 69 |
| `app/features/ai-private-search.tsx` | 69 |
| `app/features/ai-speech.tsx` | 69 |
| `app/features/ai-video.tsx` | 108 |
| `app/features/ai-writer.tsx` | 70 |
| `app/features/fitness.tsx` | 32 |
| `app/features/index.tsx` | 80 |
| `app/features/medimate.tsx` | 26 |
| `app/features/smartbuy.tsx` | 24 |
| `app/features/travelpal.tsx` | 264 |
| `app/language-selector.tsx` | 430 |
| `app/mini-apps/job-platform.tsx` | 49 |
| `app/mini-apps/onboarding.tsx` | 30 |
| `app/my-analytics.tsx` | 865 |
| `app/onboarding.tsx` | 267 |
| `app/scan-history.tsx` | 36 |
| `app/scenario/[id].tsx` | 23 |
| `src/components/AIFeedbackBar.tsx` | 141 |
| `src/components/AISearchScreen.tsx` | 65 |
| `src/components/AnalyticsReportsView.tsx` | 71 |
| `src/components/CollaborativeDocsContent.tsx` | 212 |
| `src/components/Footer.tsx` | 394 |
| `src/components/GlobalNavBar.tsx` | 117 |
| `src/components/Logo.tsx` | 41 |
| `src/components/PremiumGuard.tsx` | 109 |
| `src/components/RenewalBanner.tsx` | 105 |
| `src/components/SkeletonLoaders.tsx` | 29 |
| `src/components/SmartOnboarding.tsx` | 68 |
| `src/components/SubscriptionBadge.tsx` | 87 |
| `src/components/admin/ActivitySummaryWidget.tsx` | 23 |
| `src/components/admin/IntegrationsPanel.tsx` | 14 |
| `src/components/admin/RealityValidationPanel.tsx` | 140 |
| `src/components/admin/ThemeAuditPanel.tsx` | 192 |
| `src/components/admin/WebhookReplayPanel.tsx` | 241 |
| `src/components/gallery/FeatureDetailModal.tsx` | 221 |
| `src/components/gallery/GalleryCard.tsx` | 64 |
| `src/components/payment/ManualLinkPanel.tsx` | 38 |
| `src/components/profile/AvatarGalleryModal.tsx` | 63 |

**reviewed semantic hex** — 8 occurrences

| File | Line |
| --- | --- |
| `app/admin-activity-log.tsx` | 564 |
| `app/login.tsx` | 10 |
| `src/components/admin/SupportTicketsPanel.tsx` | 1067 |
| `src/components/admin/TranslationCoverageDashboard.tsx` | 98 |
| `src/components/auth/EnterpriseSignOutConfirmModal.tsx` | 101 |
| `src/components/auth/EnterpriseSignOutConfirmModal.tsx` | 103 |
| `src/components/executive/ExecInlinePanels.tsx` | 326 |
| `src/components/pages/CalendarInner.tsx` | 1318 |

**semantic-invert (forces dark container over white bg)** — 1 occurrence

| File | Line |
| --- | --- |
| `app/features/index.tsx` | 247 |

**theme-token-fallback** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/certificates/CertificatePrintLayoutModal.tsx` | 97 |

**variant-based (light/dark brand text)** — 1 occurrence

| File | Line |
| --- | --- |
| `src/components/Logo.tsx` | 29 |

