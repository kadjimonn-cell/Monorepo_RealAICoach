import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AppShell from '../src/components/AppShell';
import { useAuth } from '../src/context/AuthContext';
import { useAccessControl } from '../src/context/AccessControlContext';
import api from '../src/services/api';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

import { useAdminTheme } from '../src/hooks/useAdminTheme';
import { useTheme } from '../src/context/ThemeContext';
import { useTranslation } from '../src/hooks/useTranslation';

// Page-local V2-aware palette. Every surface colour pulls from the active
// V2 theme token (AC.card / AC.bgSoft / AC.border / AC.text / AC.textMuted)
// instead of the hard-coded dark-navy literals the first draft used — that
// was the "theme leak" behind the screenshot the user flagged on Apr 22 2026.
type RHRPalette = {
  bg: string;
  card: string;
  cardAlt: string;
  border: string;
  text: string;
  muted: string;
  success: string;
  warn: string;
  danger: string;
};

export default function RouteHealthReportPage() {
  const { colors } = useTheme();
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const AC = useAdminTheme();
  const C: RHRPalette = {
    bg: AC.bg,
    card: AC.card,                // V2 token
    cardAlt: AC.bgSoft,           // V2 token
    border: AC.border,            // V2 token
    text: AC.text,
    muted: AC.textMuted,
    success: colors.success,
    warn: colors.warning,
    danger: colors.error,
  };
  const { user, loading: authLoading } = useAuth();
  const { hasPermission, loading: accessLoading } = useAccessControl();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [forbidden, setForbidden] = useState(false);
  const [report, setReport] = useState<any>(null);

  const loadReport = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError('');
    setForbidden(false);
    try {
      const response = await api.get('/admin/platform-perf/route-health');
      setReport(response.data);
    } catch (e: any) {
      if (e?.response?.status === 403) {
        setForbidden(true);
      } else {
        setError(tx('routeHealth.errors.loadFailed', 'Unable to load route health metrics right now.'));
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [tx]);

  useEffect(() => {
    if (authLoading) return;
    void loadReport();
    const iv = setInterval(() => { void loadReport(true); }, 60000);
    return () => clearInterval(iv);
  }, [loadReport, authLoading, user?.user_id]);

  const canAccess = Boolean(user?.is_admin || hasPermission('employee.manage_operations'));

  const summary = report?.summary || {};
  const autoHealSuggestions = report?.auto_heal_suggestions || [];
  const routeIntegrityChecker = report?.route_integrity_checker || {};
  const checkerStatus = String(routeIntegrityChecker?.status || 'healthy').toUpperCase();
  const checkerTone = checkerStatus === 'CRITICAL' ? C.danger : checkerStatus === 'WARNING' ? C.warn : C.success;
  const missingWhitelistSegments = Array.isArray(routeIntegrityChecker?.missing_from_whitelist) ? routeIntegrityChecker.missing_from_whitelist : [];
  const uncoveredProtectedSegments = Array.isArray(routeIntegrityChecker?.uncovered_protected_segments) ? routeIntegrityChecker.uncovered_protected_segments : [];
  const redirectIssues = Array.isArray(routeIntegrityChecker?.redirect_target_issues) ? routeIntegrityChecker.redirect_target_issues : [];
  const checkerRecommendations = Array.isArray(routeIntegrityChecker?.recommendations) ? routeIntegrityChecker.recommendations : [];
  const adminTabIntegrity = report?.admin_tab_integrity || {};
  const adminTabIntegrityStatus = String(adminTabIntegrity?.status || 'healthy').toUpperCase();
  const adminTabIntegrityTone = adminTabIntegrityStatus === 'CRITICAL' ? C.danger : adminTabIntegrityStatus === 'WARNING' ? C.warn : C.success;
  const missingTabRenderers = Array.isArray(adminTabIntegrity?.missing_tab_renderers) ? adminTabIntegrity.missing_tab_renderers : [];
  const orphanRendererTabs = Array.isArray(adminTabIntegrity?.orphan_renderer_tabs) ? adminTabIntegrity.orphan_renderer_tabs : [];
  const adminTabRecommendations = Array.isArray(adminTabIntegrity?.recommendations) ? adminTabIntegrity.recommendations : [];
  const themeVisibilityAudit = report?.theme_visibility_audit || {};
  const themeVisibilityStatus = String(themeVisibilityAudit?.status || 'healthy').toUpperCase();
  const themeVisibilityTone = themeVisibilityStatus === 'CRITICAL' ? C.danger : themeVisibilityStatus === 'WARNING' ? C.warn : C.success;
  const themeRiskyFiles = Array.isArray(themeVisibilityAudit?.risky_files) ? themeVisibilityAudit.risky_files : [];
  const themeRecommendations = Array.isArray(themeVisibilityAudit?.recommendations) ? themeVisibilityAudit.recommendations : [];
  const themeSeveritySummary = typeof themeVisibilityAudit?.severity_summary === 'object' && themeVisibilityAudit?.severity_summary ? themeVisibilityAudit.severity_summary : {};
  const themeTopOffenders = Array.isArray(themeVisibilityAudit?.top_offenders) ? themeVisibilityAudit.top_offenders : [];
  const navigationLockAudit = report?.navigation_lock_audit || {};
  const navigationLockStatus = String(navigationLockAudit?.status || 'healthy').toUpperCase();
  const navigationLockTone = navigationLockStatus === 'CRITICAL' ? C.danger : navigationLockStatus === 'WARNING' ? C.warn : C.success;
  const navUnexpectedActive = Array.isArray(navigationLockAudit?.admin_unexpected_active) ? navigationLockAudit.admin_unexpected_active : [];
  const navUnlockedUserKeys = Array.isArray(navigationLockAudit?.unlocked_user_keys) ? navigationLockAudit.unlocked_user_keys : [];
  const navLockRecommendations = Array.isArray(navigationLockAudit?.recommendations) ? navigationLockAudit.recommendations : [];
  const diagnosticsSummary = report?.diagnostics_summary || {};
  const routeCrashTraces = Array.isArray(report?.route_crash_traces) ? report.route_crash_traces : [];
  const apiTimeoutTraces = Array.isArray(report?.api_timeout_traces) ? report.api_timeout_traces : [];

  return (
    <AdminRouteGate returnTo="/route-health-report">
    <AppShell>
      <View style={{ flex: 1, backgroundColor: C.bg }}>
        <ScrollView
          contentContainerStyle={{ padding: 20, paddingBottom: 100 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void loadReport(); }} tintColor={colors.info} />}
          data-testid="route-health-report-page" testID="route-health-report-page"
        >
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <View>
              <Text style={{ color: C.text, fontSize: 24, fontWeight: '800' }} data-testid="route-health-report-title" testID="route-health-report-title">{tx('routeHealth.header.title', 'Route Health Report')}</Text>
              <Text style={{ color: C.muted, fontSize: 12, marginTop: 4 }}>{tx('routeHealth.header.subtitle', 'Link integrity • Redirect success • Route latency trend')}</Text>
            </View>
            <TouchableOpacity
              onPress={() => void loadReport()}
              style={{ borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.cardAlt, paddingHorizontal: 12, paddingVertical: 8 }}
              data-testid="route-health-refresh-button" testID="route-health-refresh-button"
            >
              <Text style={{ color: C.text, fontWeight: '700', fontSize: 11 }}>{tx('routeHealth.actions.refresh', 'Refresh')}</Text>
            </TouchableOpacity>
          </View>

          {error ? <Text style={{ color: C.danger, marginBottom: 10 }} data-testid="route-health-error" testID="route-health-error">{error}</Text> : null}

          {loading ? (
            <View style={{ marginTop: 26, alignItems: 'center' }} data-testid="route-health-loading" testID="route-health-loading">
              <ActivityIndicator color={colors.info} />
            </View>
          ) : (
            <>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <MetricCard palette={C} label={tx('routeHealth.metrics.directRouteIntegrity', 'Direct Route Integrity')} value={`${Number(summary.direct_integrity_pct || 0).toFixed(1)}%`} tone={Number(summary.direct_integrity_pct || 0) >= 95 ? C.success : C.warn} testId="route-health-integrity" />
                <MetricCard palette={C} label={tx('routeHealth.metrics.legacyRedirectSuccess', 'Legacy Redirect Success')} value={`${Number(summary.redirect_success_pct || 0).toFixed(1)}%`} tone={Number(summary.redirect_success_pct || 0) >= 95 ? C.success : C.warn} testId="route-health-redirect-success" />
                <MetricCard palette={C} label={tx('routeHealth.metrics.averageLatency', 'Average Latency')} value={`${Number(summary.avg_latency_ms || 0).toFixed(0)} ms`} tone={Number(summary.avg_latency_ms || 0) <= 800 ? C.success : C.warn} testId="route-health-avg-latency" />
                <MetricCard palette={C} label={tx('routeHealth.metrics.p95Latency', 'P95 Latency')} value={`${Number(summary.p95_latency_ms || 0).toFixed(0)} ms`} tone={Number(summary.p95_latency_ms || 0) <= 1400 ? C.success : C.warn} testId="route-health-p95-latency" />
                <MetricCard palette={C} label={tx('routeHealth.metrics.runtimeHints', 'Runtime Hints')} value={`${Number(diagnosticsSummary.route_runtime_hints_count || 0)}`} tone={Number(diagnosticsSummary.route_runtime_hints_count || 0) === 0 ? C.success : C.danger} testId="route-health-runtime-hints" />
                <MetricCard palette={C} label={tx('routeHealth.metrics.apiTimeoutHints', 'API Timeout Hints')} value={`${Number(diagnosticsSummary.api_timeout_hints_count || 0)}`} tone={Number(diagnosticsSummary.api_timeout_hints_count || 0) === 0 ? C.success : C.warn} testId="route-health-api-timeout-hints" />
              </View>

              <View
                style={{
                  marginTop: 12,
                  marginBottom: 12,
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: C.border,
                  backgroundColor: C.cardAlt,
                  padding: 12,
                }}
                data-testid="route-health-gtec-scan-centralized-notice"
                testID="route-health-gtec-scan-centralized-notice"
              >
                <Text
                  style={{ color: C.text, fontSize: 12, fontWeight: '700' }}
                  data-testid="route-health-gtec-scan-centralized-title"
                  testID="route-health-gtec-scan-centralized-title"
                >
                  {tx('routeHealth.gtec.centralizedTitle', 'GTEC Scan is centralized')}
                </Text>
                <Text
                  style={{ color: C.muted, fontSize: 11, marginTop: 5 }}
                  data-testid="route-health-gtec-scan-centralized-copy"
                  testID="route-health-gtec-scan-centralized-copy"
                >
                  {tx('routeHealth.gtec.centralizedCopy', 'The upgraded autonomous C1–C5 GTEC Scan now runs from the dedicated GTEC section in Executive Dashboard to avoid duplicate legacy scan surfaces.')}
                </Text>
              </View>

              <SectionCard palette={C} title={tx('routeHealth.sections.integrityChecker', 'Internal Route-Integrity Checker')} testId="route-health-integrity-checker-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-integrity-checker-summary" testID="route-health-integrity-checker-summary">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-integrity-checker-status-label" testID="route-health-integrity-checker-status-label">{tx('routeHealth.integrityChecker.statusLabel', 'Checker status')}</Text>
                    <Text style={{ color: checkerTone, fontSize: 10, fontWeight: '900' }} data-testid="route-health-integrity-checker-status-value" testID="route-health-integrity-checker-status-value">{checkerStatus}</Text>
                  </View>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-integrity-checker-counts" testID="route-health-integrity-checker-counts">
                    {tx('routeHealth.integrityChecker.countsWithValues', 'Known segments {known} • discovered {discovered}')
                      .replace('{known}', String(Number(routeIntegrityChecker?.known_segment_count || 0)))
                      .replace('{discovered}', String(Number(routeIntegrityChecker?.discovered_segment_count || 0)))}
                  </Text>
                </View>

                {missingWhitelistSegments.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-integrity-missing-whitelist-box" testID="route-health-integrity-missing-whitelist-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-integrity-missing-whitelist-title" testID="route-health-integrity-missing-whitelist-title">{tx('routeHealth.integrityChecker.missingWhitelist', 'Missing whitelist segments')}</Text>
                    {missingWhitelistSegments.slice(0, 8).map((segment: string, idx: number) => (
                      <Text key={`${segment}-${idx}`} style={{ color: C.warn, fontSize: 10, marginTop: 4 }} data-testid={`route-health-integrity-missing-whitelist-${idx}`} testID={`route-health-integrity-missing-whitelist-${idx}`}>• {segment}</Text>
                    ))}
                  </View>
                ) : null}

                {uncoveredProtectedSegments.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-integrity-uncovered-protected-box" testID="route-health-integrity-uncovered-protected-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-integrity-uncovered-protected-title" testID="route-health-integrity-uncovered-protected-title">{tx('routeHealth.integrityChecker.uncoveredProtected', 'Protected segments without runtime probe')}</Text>
                    {uncoveredProtectedSegments.slice(0, 8).map((segment: string, idx: number) => (
                      <Text key={`${segment}-${idx}`} style={{ color: C.warn, fontSize: 10, marginTop: 4 }} data-testid={`route-health-integrity-uncovered-protected-${idx}`} testID={`route-health-integrity-uncovered-protected-${idx}`}>• {segment}</Text>
                    ))}
                  </View>
                ) : null}

                {redirectIssues.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-integrity-redirect-issues-box" testID="route-health-integrity-redirect-issues-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-integrity-redirect-issues-title" testID="route-health-integrity-redirect-issues-title">{tx('routeHealth.integrityChecker.redirectIssues', 'Redirect target issues')}</Text>
                    {redirectIssues.slice(0, 6).map((row: any, idx: number) => (
                      <Text key={`${row?.expected_target}-${idx}`} style={{ color: C.danger, fontSize: 10, marginTop: 4 }} data-testid={`route-health-integrity-redirect-issue-${idx}`} testID={`route-health-integrity-redirect-issue-${idx}`}>
                        • {row?.source_path} → {row?.expected_target}
                      </Text>
                    ))}
                  </View>
                ) : null}

                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-integrity-recommendations-box" testID="route-health-integrity-recommendations-box">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-integrity-recommendations-title" testID="route-health-integrity-recommendations-title">{tx('routeHealth.common.recommendedActions', 'Recommended actions')}</Text>
                  {(checkerRecommendations.length ? checkerRecommendations : [tx('routeHealth.common.noActionRequired', 'No action required.')]).slice(0, 6).map((item: string, idx: number) => (
                    <Text key={`${item}-${idx}`} style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-integrity-recommendation-${idx}`} testID={`route-health-integrity-recommendation-${idx}`}>• {item}</Text>
                  ))}
                </View>
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.adminTabIntegrity', 'Admin Tab Integrity')} testId="route-health-admin-tab-integrity-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-admin-tab-integrity-summary" testID="route-health-admin-tab-integrity-summary">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-admin-tab-integrity-status-label" testID="route-health-admin-tab-integrity-status-label">{tx('routeHealth.adminTab.statusLabel', 'Admin tab mapping status')}</Text>
                    <Text style={{ color: adminTabIntegrityTone, fontSize: 10, fontWeight: '900' }} data-testid="route-health-admin-tab-integrity-status-value" testID="route-health-admin-tab-integrity-status-value">{adminTabIntegrityStatus}</Text>
                  </View>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-admin-tab-integrity-counts" testID="route-health-admin-tab-integrity-counts">
                    {tx('routeHealth.adminTab.countsWithValues', 'Categories {categories} • tabs {tabs} • renderers {renderers}')
                      .replace('{categories}', String(Number(adminTabIntegrity?.total_categories || 0)))
                      .replace('{tabs}', String(Number(adminTabIntegrity?.total_tabs || 0)))
                      .replace('{renderers}', String(Number(adminTabIntegrity?.total_supported_renderers || 0)))}
                  </Text>
                </View>

                {missingTabRenderers.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-admin-tab-missing-renderers-box" testID="route-health-admin-tab-missing-renderers-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-admin-tab-missing-renderers-title" testID="route-health-admin-tab-missing-renderers-title">{tx('routeHealth.adminTab.missingRenderer', 'Tabs without renderer')}</Text>
                    {missingTabRenderers.slice(0, 8).map((tabId: string, idx: number) => (
                      <Text key={`${tabId}-${idx}`} style={{ color: C.danger, fontSize: 10, marginTop: 4 }} data-testid={`route-health-admin-tab-missing-renderer-${idx}`} testID={`route-health-admin-tab-missing-renderer-${idx}`}>• {tabId}</Text>
                    ))}
                  </View>
                ) : null}

                {orphanRendererTabs.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-admin-tab-orphan-renderers-box" testID="route-health-admin-tab-orphan-renderers-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-admin-tab-orphan-renderers-title" testID="route-health-admin-tab-orphan-renderers-title">{tx('routeHealth.adminTab.orphanRenderer', 'Renderer IDs without tab definition')}</Text>
                    {orphanRendererTabs.slice(0, 8).map((tabId: string, idx: number) => (
                      <Text key={`${tabId}-${idx}`} style={{ color: C.warn, fontSize: 10, marginTop: 4 }} data-testid={`route-health-admin-tab-orphan-renderer-${idx}`} testID={`route-health-admin-tab-orphan-renderer-${idx}`}>• {tabId}</Text>
                    ))}
                  </View>
                ) : null}

                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-admin-tab-integrity-recommendations-box" testID="route-health-admin-tab-integrity-recommendations-box">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-admin-tab-integrity-recommendations-title" testID="route-health-admin-tab-integrity-recommendations-title">{tx('routeHealth.common.recommendedActions', 'Recommended actions')}</Text>
                  {(adminTabRecommendations.length ? adminTabRecommendations : [tx('routeHealth.common.noActionRequired', 'No action required.')]).slice(0, 6).map((item: string, idx: number) => (
                    <Text key={`${item}-${idx}`} style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-admin-tab-integrity-recommendation-${idx}`} testID={`route-health-admin-tab-integrity-recommendation-${idx}`}>• {item}</Text>
                  ))}
                </View>
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.themeVisibility', 'Theme Visibility Integrity')} testId="route-health-theme-visibility-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-theme-visibility-summary" testID="route-health-theme-visibility-summary">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-theme-visibility-status-label" testID="route-health-theme-visibility-status-label">{tx('routeHealth.themeVisibility.statusLabel', 'Theme visibility status')}</Text>
                    <Text style={{ color: themeVisibilityTone, fontSize: 10, fontWeight: '900' }} data-testid="route-health-theme-visibility-status-value" testID="route-health-theme-visibility-status-value">{themeVisibilityStatus}</Text>
                  </View>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-theme-visibility-counts" testID="route-health-theme-visibility-counts">
                    {tx('routeHealth.themeVisibility.countsWithValues', 'Monitored files {monitored} • risky files {risky}')
                      .replace('{monitored}', String(Number(themeVisibilityAudit?.monitored_file_count || 0)))
                      .replace('{risky}', String(Number(themeVisibilityAudit?.risky_file_count || 0)))}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 3 }} data-testid="route-health-theme-visibility-severity-counts" testID="route-health-theme-visibility-severity-counts">
                    {tx('routeHealth.themeVisibility.severityWithValues', 'Critical {critical} • High {high} • Medium {medium} • Low {low}')
                      .replace('{critical}', String(Number(themeSeveritySummary?.critical || 0)))
                      .replace('{high}', String(Number(themeSeveritySummary?.high || 0)))
                      .replace('{medium}', String(Number(themeSeveritySummary?.medium || 0)))
                      .replace('{low}', String(Number(themeSeveritySummary?.low || 0)))}
                  </Text>
                </View>

                {themeRiskyFiles.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-theme-visibility-risky-files-box" testID="route-health-theme-visibility-risky-files-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-theme-visibility-risky-files-title" testID="route-health-theme-visibility-risky-files-title">{tx('routeHealth.themeVisibility.riskyFiles', 'Files requiring dark/light tokenization')}</Text>
                    {themeRiskyFiles.slice(0, 8).map((filePath: string, idx: number) => (
                      <Text key={`${filePath}-${idx}`} style={{ color: C.warn, fontSize: 10, marginTop: 4 }} data-testid={`route-health-theme-visibility-risky-file-${idx}`} testID={`route-health-theme-visibility-risky-file-${idx}`}>• {filePath.split('/').slice(-3).join('/')}</Text>
                    ))}
                  </View>
                ) : null}

                {themeTopOffenders.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-theme-top-offenders-box" testID="route-health-theme-top-offenders-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-theme-top-offenders-title" testID="route-health-theme-top-offenders-title">{tx('routeHealth.themeVisibility.topOffenders', 'Top theme offenders (severity scoring)')}</Text>
                    {themeTopOffenders.slice(0, 8).map((row: any, idx: number) => (
                      <Text key={`${row?.file}-${idx}`} style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-theme-top-offender-${idx}`} testID={`route-health-theme-top-offender-${idx}`}>
                        • {String(row?.severity || 'none').toUpperCase()} ({Number(row?.score || 0)}) — {String(row?.file || '').split('/').slice(-3).join('/')}
                      </Text>
                    ))}
                  </View>
                ) : null}

                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-theme-visibility-recommendations-box" testID="route-health-theme-visibility-recommendations-box">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-theme-visibility-recommendations-title" testID="route-health-theme-visibility-recommendations-title">{tx('routeHealth.common.recommendedActions', 'Recommended actions')}</Text>
                  {(themeRecommendations.length ? themeRecommendations : [tx('routeHealth.common.noActionRequired', 'No action required.')]).slice(0, 6).map((item: string, idx: number) => (
                    <Text key={`${item}-${idx}`} style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-theme-visibility-recommendation-${idx}`} testID={`route-health-theme-visibility-recommendation-${idx}`}>• {item}</Text>
                  ))}
                </View>
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.navigationLock', 'Navigation Lock Integrity')} testId="route-health-navigation-lock-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-navigation-lock-summary" testID="route-health-navigation-lock-summary">
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-navigation-lock-status-label" testID="route-health-navigation-lock-status-label">{tx('routeHealth.navigationLock.statusLabel', 'Navigation lock status')}</Text>
                    <Text style={{ color: navigationLockTone, fontSize: 10, fontWeight: '900' }} data-testid="route-health-navigation-lock-status-value" testID="route-health-navigation-lock-status-value">{navigationLockStatus}</Text>
                  </View>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-navigation-lock-counts" testID="route-health-navigation-lock-counts">
                    {tx('routeHealth.navigationLock.countsWithValues', 'Locked admin keys {locked} • active admin keys {active}')
                      .replace('{locked}', String(Array.isArray(navigationLockAudit?.locked_admin_keys) ? navigationLockAudit.locked_admin_keys.length : 0))
                      .replace('{active}', String(Array.isArray(navigationLockAudit?.active_admin_nav_keys) ? navigationLockAudit.active_admin_nav_keys.length : 0))}
                  </Text>
                </View>

                {navUnexpectedActive.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-navigation-lock-unexpected-active-box" testID="route-health-navigation-lock-unexpected-active-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-navigation-lock-unexpected-active-title" testID="route-health-navigation-lock-unexpected-active-title">{tx('routeHealth.navigationLock.unapprovedEntries', 'Unapproved active ADMIN entries')}</Text>
                    {navUnexpectedActive.slice(0, 8).map((key: string, idx: number) => (
                      <Text key={`${key}-${idx}`} style={{ color: C.danger, fontSize: 10, marginTop: 4 }} data-testid={`route-health-navigation-lock-unexpected-active-${idx}`} testID={`route-health-navigation-lock-unexpected-active-${idx}`}>• {key}</Text>
                    ))}
                  </View>
                ) : null}

                {navUnlockedUserKeys.length ? (
                  <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-navigation-lock-unlocked-user-box" testID="route-health-navigation-lock-unlocked-user-box">
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-navigation-lock-unlocked-user-title" testID="route-health-navigation-lock-unlocked-user-title">{tx('routeHealth.navigationLock.unlockedUserKeys', 'User nav keys outside lock set')}</Text>
                    {navUnlockedUserKeys.slice(0, 8).map((key: string, idx: number) => (
                      <Text key={`${key}-${idx}`} style={{ color: C.warn, fontSize: 10, marginTop: 4 }} data-testid={`route-health-navigation-lock-unlocked-user-${idx}`} testID={`route-health-navigation-lock-unlocked-user-${idx}`}>• {key}</Text>
                    ))}
                  </View>
                ) : null}

                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid="route-health-navigation-lock-recommendations-box" testID="route-health-navigation-lock-recommendations-box">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-navigation-lock-recommendations-title" testID="route-health-navigation-lock-recommendations-title">{tx('routeHealth.common.recommendedActions', 'Recommended actions')}</Text>
                  {(navLockRecommendations.length ? navLockRecommendations : [tx('routeHealth.common.noActionRequired', 'No action required.')]).slice(0, 6).map((item: string, idx: number) => (
                    <Text key={`${item}-${idx}`} style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-navigation-lock-recommendation-${idx}`} testID={`route-health-navigation-lock-recommendation-${idx}`}>• {item}</Text>
                  ))}
                </View>
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.legacyRedirectChecks', 'Legacy Redirect Checks')} testId="route-health-legacy-card">
                {(report?.legacy_redirects || []).map((row: any, idx: number) => (
                  <RowItem palette={C}
                    key={`${row.path}-${idx}`}
                    title={row.path}
                    subtitle={tx('routeHealth.legacy.expectedActualWithValues', 'expected: {expected} • actual: {actual}')
                      .replace('{expected}', String(row.expected_target))
                      .replace('{actual}', String(row.final_path || '-'))}
                    value={`${row.status_code || 0} • ${Number(row.latency_ms || 0).toFixed(0)} ms`}
                    good={Boolean(row.redirect_ok)}
                    testId={`legacy-row-${idx}`}
                  />
                ))}
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.directFeatureRoutes', 'Direct Feature Routes')} testId="route-health-direct-card">
                {(report?.direct_routes || []).slice(0, 20).map((row: any, idx: number) => (
                  <RowItem palette={C}
                    key={`${row.path}-${idx}`}
                    title={row.path}
                    subtitle={tx('routeHealth.direct.finalWithHints', 'final: {final}{runtimeHint}{whiteHint}')
                      .replace('{final}', String(row.final_path || '-'))
                      .replace('{runtimeHint}', row.runtime_error_hint ? tx('routeHealth.direct.runtimeHint', ' • runtime-error-hint') : '')
                      .replace('{whiteHint}', row.white_screen_hint ? tx('routeHealth.direct.whiteScreenHint', ' • white-screen-hint') : '')}
                    value={`${row.status_code || 0} • ${Number(row.latency_ms || 0).toFixed(0)} ms`}
                    good={Boolean(row.healthy)}
                    testId={`direct-row-${idx}`}
                  />
                ))}
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.crashWhiteScreenDiagnostics', 'Crash + White-screen Diagnostics')} testId="route-health-crash-diagnostics-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-crash-diagnostics-summary" testID="route-health-crash-diagnostics-summary">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-crash-diagnostics-summary-title" testID="route-health-crash-diagnostics-summary-title">
                    {tx('routeHealth.crash.summaryTitle', 'Current diagnostic counters')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-crash-diagnostics-summary-counts" testID="route-health-crash-diagnostics-summary-counts">
                    {tx('routeHealth.crash.summaryCounts', 'Runtime {runtime} • White-screen {white} • Probe exceptions {exceptions}')
                      .replace('{runtime}', String(Number(diagnosticsSummary.route_runtime_hints_count || 0)))
                      .replace('{white}', String(Number(diagnosticsSummary.route_white_screen_hints_count || 0)))
                      .replace('{exceptions}', String(Number(diagnosticsSummary.route_probe_exception_count || 0)))}
                  </Text>
                </View>

                {routeCrashTraces.length === 0 ? (
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="route-health-crash-diagnostics-empty" testID="route-health-crash-diagnostics-empty">
                    {tx('routeHealth.crash.empty', 'No crash/white-screen traces detected in current probe window.')}
                  </Text>
                ) : routeCrashTraces.slice(0, 8).map((row: any, idx: number) => (
                  <View key={`${row?.path}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`route-health-crash-trace-row-${idx}`} testID={`route-health-crash-trace-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }} numberOfLines={1}>{row?.path || '-'}</Text>
                      <Text style={{ color: row?.runtime_error_hint ? C.danger : C.warn, fontSize: 10, fontWeight: '900' }} data-testid={`route-health-crash-trace-signature-${idx}`} testID={`route-health-crash-trace-signature-${idx}`}>
                        {String(row?.crash_signature || 'trace').toUpperCase()}
                      </Text>
                    </View>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-crash-trace-meta-${idx}`} testID={`route-health-crash-trace-meta-${idx}`}>
                      {tx('routeHealth.crash.meta', 'status {status} • latency {latency} ms • final {final}')
                        .replace('{status}', String(row?.status_code || 0))
                        .replace('{latency}', Number(row?.latency_ms || 0).toFixed(0))
                        .replace('{final}', String(row?.final_path || '-'))}
                    </Text>
                    {row?.trace_excerpt ? (
                      <Text style={{ color: C.text, fontSize: 10, marginTop: 4, lineHeight: 16 }} data-testid={`route-health-crash-trace-excerpt-${idx}`} testID={`route-health-crash-trace-excerpt-${idx}`}>
                        {String(row.trace_excerpt)}
                      </Text>
                    ) : null}
                  </View>
                ))}
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.apiTimeoutDiagnostics', 'API Timeout + Backend Error Traces')} testId="route-health-api-timeout-card">
                <View style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 9 }} data-testid="route-health-api-timeout-summary" testID="route-health-api-timeout-summary">
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }} data-testid="route-health-api-timeout-summary-title" testID="route-health-api-timeout-summary-title">
                    {tx('routeHealth.apiTimeout.summaryTitle', 'Protected API diagnostic counters')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 5 }} data-testid="route-health-api-timeout-summary-counts" testID="route-health-api-timeout-summary-counts">
                    {tx('routeHealth.apiTimeout.summaryCounts', 'Timeout hints {timeout} • API errors {errors} • 5xx {fiveXX}')
                      .replace('{timeout}', String(Number(diagnosticsSummary.api_timeout_hints_count || 0)))
                      .replace('{errors}', String(Number(diagnosticsSummary.api_error_hints_count || 0)))
                      .replace('{fiveXX}', String(Number(diagnosticsSummary.api_5xx_count || 0)))}
                  </Text>
                </View>

                {apiTimeoutTraces.length === 0 ? (
                  <Text style={{ color: C.muted, fontSize: 11 }} data-testid="route-health-api-timeout-empty" testID="route-health-api-timeout-empty">
                    {tx('routeHealth.apiTimeout.empty', 'No API timeout/error traces detected in current probe window.')}
                  </Text>
                ) : apiTimeoutTraces.slice(0, 8).map((row: any, idx: number) => (
                  <View key={`${row?.id}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`route-health-api-timeout-trace-row-${idx}`} testID={`route-health-api-timeout-trace-row-${idx}`}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                      <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }} numberOfLines={1}>{row?.label || row?.id || '-'}</Text>
                      <Text style={{ color: row?.api_error_hint ? C.danger : C.warn, fontSize: 10, fontWeight: '900' }} data-testid={`route-health-api-timeout-trace-category-${idx}`} testID={`route-health-api-timeout-trace-category-${idx}`}>
                        {String(row?.api_error_category || 'none').toUpperCase()}
                      </Text>
                    </View>
                    <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }} data-testid={`route-health-api-timeout-trace-meta-${idx}`} testID={`route-health-api-timeout-trace-meta-${idx}`}>
                      {tx('routeHealth.apiTimeout.meta', '{routePath} • {apiPath} • status {status} • latency {latency} ms')
                        .replace('{routePath}', String(row?.route_path || '-'))
                        .replace('{apiPath}', String(row?.api_path || '-'))
                        .replace('{status}', String(row?.api_status_code || 0))
                        .replace('{latency}', Number(row?.latency_ms || 0).toFixed(0))}
                    </Text>
                    {row?.api_trace_excerpt ? (
                      <Text style={{ color: C.text, fontSize: 10, marginTop: 4, lineHeight: 16 }} data-testid={`route-health-api-timeout-trace-excerpt-${idx}`} testID={`route-health-api-timeout-trace-excerpt-${idx}`}>
                        {String(row.api_trace_excerpt)}
                      </Text>
                    ) : null}
                  </View>
                ))}
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.trend14Day', '14-Day Trend')} testId="route-health-trend-card">
                {(report?.history || []).slice(-10).map((row: any, idx: number) => (
                  <View key={`${row.timestamp}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={`trend-row-${idx}`} testID={`trend-row-${idx}`}>
                    <Text style={{ color: C.muted, fontSize: 10 }}>{new Date(row.timestamp).toLocaleString()}</Text>
                    <Text style={{ color: C.text, marginTop: 3, fontSize: 11 }}>
                      {tx('routeHealth.trend.integrityRedirectP95WithValues', 'Integrity {integrity}% • Redirect {redirect}% • p95 {p95} ms')
                        .replace('{integrity}', Number(row.direct_integrity_pct || 0).toFixed(1))
                        .replace('{redirect}', Number(row.redirect_success_pct || 0).toFixed(1))
                        .replace('{p95}', Number(row.p95_latency_ms || 0).toFixed(0))}
                    </Text>
                  </View>
                ))}
              </SectionCard>

              <SectionCard palette={C} title={tx('routeHealth.sections.autoHealSuggestions', 'Auto-Heal Suggestions')} testId="route-health-auto-heal-card">
                {autoHealSuggestions.map((item: any, idx: number) => {
                  const tone = item.severity === 'high' ? C.danger : item.severity === 'medium' ? C.warn : C.success;
                  return (
                    <View key={`${item.category}-${idx}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, backgroundColor: C.cardAlt, paddingHorizontal: 12, paddingVertical: 10 }} data-testid={`route-health-auto-heal-row-${idx}`} testID={`route-health-auto-heal-row-${idx}`}>
                      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                        <Text style={{ color: C.text, fontSize: 12, fontWeight: '800', flex: 1 }}>{item.title}</Text>
                        <Text style={{ color: tone, fontSize: 10, fontWeight: '900', textTransform: 'uppercase' }}>{item.severity}</Text>
                      </View>
                      <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>{item.threshold}</Text>
                      <Text style={{ color: C.text, fontSize: 11, marginTop: 8, lineHeight: 18 }}>{item.action}</Text>
                      {Array.isArray(item.evidence) && item.evidence.length > 0 ? (
                        <View style={{ marginTop: 8, gap: 4 }}>
                          {item.evidence.map((evidence: string, evidenceIdx: number) => (
                            <Text key={`${item.category}-evidence-${evidenceIdx}`} style={{ color: tone, fontSize: 10 }} data-testid={`route-health-auto-heal-evidence-${idx}-${evidenceIdx}`} testID={`route-health-auto-heal-evidence-${idx}-${evidenceIdx}`}>• {evidence}</Text>
                          ))}
                        </View>
                      ) : null}
                    </View>
                  );
                })}
              </SectionCard>
            </>
          )}
        </ScrollView>
      </View>
    </AppShell>
    </AdminRouteGate>
  );
}

function MetricCard({ label, value, tone, testId, palette }: { label: string; value: string; tone: string; testId: string; palette: RHRPalette }) {
  return (
    <View style={{ flexBasis: '48%', minWidth: 180, borderRadius: 12, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 12 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.muted, fontSize: 10, textTransform: 'uppercase', fontWeight: '700' }}>{label}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8 }}>
        <Ionicons name="pulse-outline" size={14} color={tone} />
        <Text style={{ color: tone, fontSize: 17, fontWeight: '900' }}>{value}</Text>
      </View>
    </View>
  );
}

function SectionCard({ title, children, testId, palette }: { title: string; children: React.ReactNode; testId: string; palette: RHRPalette }) {
  return (
    <View style={{ marginTop: 14, borderRadius: 14, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.card, padding: 14 }} data-testid={testId} testID={testId}>
      <Text style={{ color: palette.text, fontSize: 14, fontWeight: '800', marginBottom: 10 }}>{title}</Text>
      <View style={{ gap: 8 }}>{children}</View>
    </View>
  );
}

function RowItem({ title, subtitle, value, good, testId, palette }: { title: string; subtitle: string; value: string; good: boolean; testId: string; palette: RHRPalette }) {
  const { t } = useTranslation();
  const healthyLabel = (() => {
    const value = t('routeHealth.row.healthy');
    return value === 'routeHealth.row.healthy' ? 'HEALTHY' : value;
  })();
  const issueLabel = (() => {
    const value = t('routeHealth.row.issue');
    return value === 'routeHealth.row.issue' ? 'ISSUE' : value;
  })();
  return (
    <View style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, backgroundColor: palette.cardAlt, paddingHorizontal: 10, paddingVertical: 8 }} data-testid={testId} testID={testId}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text style={{ color: palette.text, fontSize: 11, fontWeight: '700', flex: 1 }} numberOfLines={1}>{title}</Text>
        <Text style={{ color: good ? palette.success : palette.danger, fontSize: 10, fontWeight: '800' }}>{good ? healthyLabel : issueLabel}</Text>
      </View>
      <Text style={{ color: palette.muted, fontSize: 10, marginTop: 3 }} numberOfLines={1}>{subtitle}</Text>
      <Text style={{ color: palette.text, fontSize: 10, marginTop: 2 }}>{value}</Text>
    </View>
  );
}
