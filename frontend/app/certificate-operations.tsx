import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import AppShell from '../src/components/AppShell';
import api from '../src/services/api';
import { useTheme } from '../src/context/ThemeContext';
import { useAuth } from '../src/context/AuthContext';
import { useTranslation } from '../src/hooks/useTranslation';
import { GLSContainer, GLSGrid, GLSGridItem, GLSSection, useGLSBreakpoint } from '../src/components/layout/GlobalLayoutSystem';
import { hasAdminConsoleVisibility } from '../src/utils/adminAccess';
import { AdminRouteGate } from '../src/components/auth/AdminRouteGate';

const RANGE_OPTIONS = ['7d', '30d', '90d', 'all'];

const toPct = (value: number) => `${Number(value || 0).toFixed(1)}%`;

export default function CertificateOperationsPage() {
  const { t } = useTranslation();
  t('i18n.route.certificate-operations.probe');
  const { colors, darkMode } = useTheme();
  const { user } = useAuth();
  const router = useRouter();
  const { isMobile, isTablet } = useGLSBreakpoint();

  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);

  const C = useMemo(() => ({
    bg: colors.bg,
    paper: colors.card,
    card: colors.cardMuted || colors.card,
    border: colors.border,
    borderSoft: colors.borderLight || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    primary: colors.primary,
    info: colors.notificationInfo || colors.primary,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    ink: darkMode ? colors.cardMuted : colors.text,
    successBg: darkMode ? 'rgba(16,185,129,0.16)' : '#DCFCE7',
    dangerBg: darkMode ? 'rgba(220,38,38,0.18)' : '#FEF2F2',
  }), [colors, darkMode]);

  const isAdmin = hasAdminConsoleVisibility(user as any);
  const isNarrow = isMobile || isTablet;

  const [range, setRange] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [analytics, setAnalytics] = useState<any>(null);
  const [revokedReasonRows, setRevokedReasonRows] = useState<{ reason: string; count: number }[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [analyticsRes, revokedRes] = await Promise.all([
        api.get('/ai-learn/admin/certificate-analytics', { params: { range } }),
        api.get('/ai-learn/admin/certificates', { params: { status: 'revoked', limit: 400 } }),
      ]);

      const payload = analyticsRes.data || null;
      const revoked = Array.isArray(revokedRes?.data?.certificates) ? revokedRes.data.certificates : [];
      const reasonMap = revoked.reduce((acc: Record<string, number>, row: any) => {
        const reason = String(row?.revocation_reason || '').trim() || tx('certificateOperations.revocation.unknownReason', 'Unspecified revocation reason');
        acc[reason] = (acc[reason] || 0) + 1;
        return acc;
      }, {});
      const reasonRows = Object.entries(reasonMap)
        .map(([reason, count]) => ({ reason, count: Number(count || 0) }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8);

      setAnalytics(payload);
      setRevokedReasonRows(reasonRows);
    } catch (e: any) {
      setError(e?.response?.data?.detail || tx('certificateOperations.errors.loadFailed', 'Unable to load certificate operations analytics.'));
    } finally {
      setLoading(false);
    }
  }, [isAdmin, range, tx]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = analytics?.summary || {};
  const statusMix = Array.isArray(analytics?.status_mix) ? analytics.status_mix : [];
  const topCourses = Array.isArray(analytics?.top_courses) ? analytics.top_courses : [];
  const timeseries = Array.isArray(analytics?.timeseries) ? analytics.timeseries : [];
  const recommendedActions = Array.isArray(analytics?.executive_report?.recommended_actions)
    ? analytics.executive_report.recommended_actions
    : [];

  const revokedCount = useMemo(() => {
    return Number(statusMix.find((row: any) => String(row?.status || '').toLowerCase() === 'revoked')?.count || 0);
  }, [statusMix]);

  const issuedCount = Number(summary?.certificates_issued || 0);
  const revocationRate = issuedCount > 0 ? (revokedCount / issuedCount) * 100 : 0;
  const verifierTraffic = Number(summary?.verifier_views_total || 0);

  const maxTraffic = useMemo(() => {
    return Math.max(
      1,
      ...timeseries.map((row: any) => Number(row?.verifier_views || 0)),
    );
  }, [timeseries]);

  return (
    <AdminRouteGate returnTo="/certificate-operations">
    <AppShell>
      <ScrollView
        style={{ flex: 1, backgroundColor: C.bg }}
        contentContainerStyle={{ paddingBottom: 80 }}
        data-testid="certificate-operations-page"
        testID="certificate-operations-page"
      >
        <GLSSection noVerticalPadding style={{ paddingTop: isNarrow ? 14 : 20, paddingBottom: 18 }} testID="certificate-operations-main-section">
          <GLSContainer noPadding testID="certificate-operations-main-container">
            <>
                <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 14, backgroundColor: C.paper, padding: isNarrow ? 14 : 18 }} data-testid="certificate-operations-hero" testID="certificate-operations-hero">
                  <Text style={{ color: C.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.4 }} data-testid="certificate-operations-overline" testID="certificate-operations-overline">
                    {tx('certificateOperations.hero.overline', 'CERTIFICATE OPERATIONS')}
                  </Text>
                  <Text style={{ color: C.text, fontSize: isNarrow ? 30 : 42, lineHeight: isNarrow ? 36 : 46, marginTop: 8, fontWeight: '900' }} data-testid="certificate-operations-title" testID="certificate-operations-title">
                    {tx('certificateOperations.hero.title', 'Enterprise certificate governance dashboard')}
                  </Text>
                  <Text style={{ color: C.muted, fontSize: 13, lineHeight: 22, marginTop: 10 }} data-testid="certificate-operations-subtitle" testID="certificate-operations-subtitle">
                    {tx('certificateOperations.hero.subtitle', 'Track issuance, revocation risk, verification traffic, top-performing courses, and revocation reasons from one operational command center.')}
                  </Text>

                  <View style={{ marginTop: 12, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="certificate-operations-range-selector" testID="certificate-operations-range-selector">
                    {RANGE_OPTIONS.map((option) => {
                      const active = range === option;
                      return (
                        <TouchableOpacity
                          key={option}
                          onPress={() => setRange(option)}
                          style={{
                            backgroundColor: active ? C.primary : C.card,
                            borderWidth: 1,
                            borderColor: active ? C.primary : C.border,
                            borderRadius: 999,
                            paddingHorizontal: 12,
                            paddingVertical: 8,
                          }}
                          data-testid={`certificate-operations-range-${option}`}
                          testID={`certificate-operations-range-${option}`}
                        >
                          <Text style={{ color: active ? (colors.primaryText || colors.buttonText || colors.text) : C.text, fontSize: 10, fontWeight: '800' }}>{option.toUpperCase()}</Text>
                        </TouchableOpacity>
                      );
                    })}
                    <TouchableOpacity onPress={() => void load()} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="certificate-operations-refresh-button" testID="certificate-operations-refresh-button">
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{tx('certificateOperations.actions.refresh', 'Refresh')}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => router.push('/certificate-gallery' as any)} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="certificate-operations-open-gallery-button" testID="certificate-operations-open-gallery-button">
                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{tx('certificateOperations.actions.openGallery', 'Open Gallery')}</Text>
                    </TouchableOpacity>
                  </View>

                  {error ? (
                    <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.error, borderRadius: 10, backgroundColor: C.dangerBg, padding: 10 }} data-testid="certificate-operations-error-banner" testID="certificate-operations-error-banner">
                      <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }} data-testid="certificate-operations-error-text" testID="certificate-operations-error-text">
                        {error}
                      </Text>
                    </View>
                  ) : null}
                </View>

                {loading ? (
                  <View style={{ marginTop: 12, borderWidth: 1, borderColor: C.border, borderRadius: 14, backgroundColor: C.paper, padding: 28, alignItems: 'center' }} data-testid="certificate-operations-loading-state" testID="certificate-operations-loading-state">
                    <ActivityIndicator size="large" color={C.primary} />
                    <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }} data-testid="certificate-operations-loading-text" testID="certificate-operations-loading-text">
                      {tx('certificateOperations.states.loading', 'Loading operations analytics...')}
                    </Text>
                  </View>
                ) : (
                  <>
                    <View style={{ marginTop: 12 }} data-testid="certificate-operations-kpi-grid" testID="certificate-operations-kpi-grid">
                      <GLSGrid columns={12} gap={10}>
                        {[
                          {
                            key: 'issued',
                            label: tx('certificateOperations.kpis.issued', 'Certificates issued'),
                            value: String(issuedCount),
                            color: C.primary,
                            icon: 'ribbon-outline',
                          },
                          {
                            key: 'revoked',
                            label: tx('certificateOperations.kpis.revoked', 'Revoked certificates'),
                            value: String(revokedCount),
                            color: C.error,
                            icon: 'warning-outline',
                          },
                          {
                            key: 'revocation-rate',
                            label: tx('certificateOperations.kpis.revocationRate', 'Revocation rate'),
                            value: toPct(revocationRate),
                            color: C.warning,
                            icon: 'pulse-outline',
                          },
                          {
                            key: 'traffic',
                            label: tx('certificateOperations.kpis.verificationTraffic', 'Verification traffic'),
                            value: String(verifierTraffic),
                            color: C.info,
                            icon: 'analytics-outline',
                          },
                        ].map((card) => (
                          <GLSGridItem key={card.key} span={isMobile ? 12 : isTablet ? 6 : 3} spanMobile={12} spanTablet={6} spanDesktop={3}>
                            <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid={`certificate-operations-kpi-${card.key}`} testID={`certificate-operations-kpi-${card.key}`}>
                              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                                <Ionicons name={card.icon as any} size={14} color={card.color} />
                                <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
                              </View>
                              <Text style={{ color: card.color, fontSize: 26, marginTop: 8, fontWeight: '900' }} data-testid={`certificate-operations-kpi-${card.key}-value`} testID={`certificate-operations-kpi-${card.key}-value`}>
                                {card.value}
                              </Text>
                            </View>
                          </GLSGridItem>
                        ))}
                      </GLSGrid>
                    </View>

                    <View style={{ marginTop: 12 }}>
                      <GLSGrid columns={12} gap={10}>
                        <GLSGridItem span={isNarrow ? 12 : 7} spanMobile={12} spanTablet={12} spanDesktop={7}>
                          <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-operations-traffic-card" testID="certificate-operations-traffic-card">
                            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="certificate-operations-traffic-title" testID="certificate-operations-traffic-title">
                              {tx('certificateOperations.traffic.title', 'Verification traffic trend')}
                            </Text>
                            <View style={{ marginTop: 10, gap: 8 }}>
                              {timeseries.slice(-8).map((row: any, index: number) => {
                                const views = Number(row?.verifier_views || 0);
                                const widthPct = Math.max(8, Math.round((views / maxTraffic) * 100));
                                return (
                                  <View key={`${row?.bucket || index}`} style={{ gap: 4 }} data-testid={`certificate-operations-traffic-row-${index}`} testID={`certificate-operations-traffic-row-${index}`}>
                                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                                      <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{String(row?.bucket || '-')}</Text>
                                      <Text style={{ color: C.text, fontSize: 10, fontWeight: '800' }}>{views}</Text>
                                    </View>
                                    <View style={{ height: 10, borderRadius: 999, backgroundColor: C.card }}>
                                      <View style={{ width: `${widthPct}%`, height: 10, borderRadius: 999, backgroundColor: C.info }} />
                                    </View>
                                  </View>
                                );
                              })}
                            </View>
                          </View>
                        </GLSGridItem>

                        <GLSGridItem span={isNarrow ? 12 : 5} spanMobile={12} spanTablet={12} spanDesktop={5}>
                          <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-operations-reasons-card" testID="certificate-operations-reasons-card">
                            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="certificate-operations-reasons-title" testID="certificate-operations-reasons-title">
                              {tx('certificateOperations.revocation.title', 'Top revoked reasons')}
                            </Text>
                            <View style={{ marginTop: 10, gap: 8 }}>
                              {revokedReasonRows.length === 0 ? (
                                <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-operations-reasons-empty" testID="certificate-operations-reasons-empty">
                                  {tx('certificateOperations.revocation.empty', 'No revoked reasons available for this range.')}
                                </Text>
                              ) : revokedReasonRows.map((row, index) => (
                                <View key={`${row.reason}-${index}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: C.card, padding: 10, flexDirection: 'row', justifyContent: 'space-between', gap: 10 }} data-testid={`certificate-operations-reason-row-${index}`} testID={`certificate-operations-reason-row-${index}`}>
                                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700', flex: 1 }}>{row.reason}</Text>
                                  <Text style={{ color: C.error, fontSize: 12, fontWeight: '900' }} data-testid={`certificate-operations-reason-row-${index}-count`} testID={`certificate-operations-reason-row-${index}-count`}>
                                    {row.count}
                                  </Text>
                                </View>
                              ))}
                            </View>
                          </View>
                        </GLSGridItem>
                      </GLSGrid>
                    </View>

                    <View style={{ marginTop: 12 }}>
                      <GLSGrid columns={12} gap={10}>
                        <GLSGridItem span={isNarrow ? 12 : 7} spanMobile={12} spanTablet={12} spanDesktop={7}>
                          <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-operations-top-courses-card" testID="certificate-operations-top-courses-card">
                            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="certificate-operations-top-courses-title" testID="certificate-operations-top-courses-title">
                              {tx('certificateOperations.courses.title', 'Top courses by certificate sharing')}
                            </Text>
                            <View style={{ marginTop: 10, gap: 8 }}>
                              {topCourses.slice(0, 6).map((course: any, index: number) => (
                                <View key={`${course?.course_id || index}`} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, backgroundColor: index === 0 ? C.successBg : C.card, padding: 10 }} data-testid={`certificate-operations-course-row-${index}`} testID={`certificate-operations-course-row-${index}`}>
                                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid={`certificate-operations-course-row-${index}-title`} testID={`certificate-operations-course-row-${index}-title`}>
                                    {String(course?.course_title || tx('certificateOperations.courses.unknownCourse', 'Course'))}
                                  </Text>
                                  <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>
                                    {tx('certificateOperations.courses.metricsWithValues', 'Completions {completions} · Issued {issued} · Shared {shared}')
                                      .replace('{completions}', String(course?.completions || 0))
                                      .replace('{issued}', String(course?.certificates_issued || 0))
                                      .replace('{shared}', String(course?.certificates_shared || 0))}
                                  </Text>
                                  <Text style={{ color: C.primary, fontSize: 10, marginTop: 4, fontWeight: '700' }} data-testid={`certificate-operations-course-row-${index}-conversion`} testID={`certificate-operations-course-row-${index}-conversion`}>
                                    {tx('certificateOperations.courses.conversionWithValues', 'Completion→Share {completion}% · Issue→Share {issue}%')
                                      .replace('{completion}', toPct(course?.completion_to_share_pct || 0))
                                      .replace('{issue}', toPct(course?.issue_to_share_pct || 0))}
                                  </Text>
                                </View>
                              ))}
                            </View>
                          </View>
                        </GLSGridItem>

                        <GLSGridItem span={isNarrow ? 12 : 5} spanMobile={12} spanTablet={12} spanDesktop={5}>
                          <View style={{ borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, backgroundColor: C.paper, padding: 12 }} data-testid="certificate-operations-recommendations-card" testID="certificate-operations-recommendations-card">
                            <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="certificate-operations-recommendations-title" testID="certificate-operations-recommendations-title">
                              {tx('certificateOperations.recommendations.title', 'Recommended actions')}
                            </Text>
                            <View style={{ marginTop: 10, gap: 8 }}>
                              {recommendedActions.length === 0 ? (
                                <Text style={{ color: C.muted, fontSize: 11 }} data-testid="certificate-operations-recommendations-empty" testID="certificate-operations-recommendations-empty">
                                  {tx('certificateOperations.recommendations.empty', 'No recommendations available.')}
                                </Text>
                              ) : recommendedActions.map((item: string, index: number) => (
                                <View key={`${item}-${index}`} style={{ flexDirection: 'row', gap: 7, alignItems: 'flex-start' }} data-testid={`certificate-operations-recommendation-row-${index}`} testID={`certificate-operations-recommendation-row-${index}`}>
                                  <Ionicons name="sparkles" size={14} color={C.primary} style={{ marginTop: 1 }} />
                                  <Text style={{ color: C.muted, fontSize: 11, lineHeight: 18, flex: 1 }}>{item}</Text>
                                </View>
                              ))}
                            </View>
                          </View>
                        </GLSGridItem>
                      </GLSGrid>
                    </View>
                  </>
                )}
              </>
          </GLSContainer>
        </GLSSection>
      </ScrollView>
    </AppShell>
    </AdminRouteGate>
  );
}
