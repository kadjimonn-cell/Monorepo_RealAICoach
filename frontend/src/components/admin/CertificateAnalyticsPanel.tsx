import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const RANGE_OPTIONS = ['7d', '30d', '90d', 'all'];

const tx = (_key: string, fallback: string) => fallback;

const formatPct = (value) => `${Number(value || 0).toFixed(1)}%`;

const formatLabel = (value) => String(value || '').replace(/_/g, ' ').toUpperCase();

const funnelRatio = (current, previous) => {
  if (!previous) return '100.0%';
  return `${((Number(current || 0) / Math.max(Number(previous || 0), 1)) * 100).toFixed(1)}%`;
};

export default function CertificateAnalyticsPanel({ colors }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };


  const AC = useAdminTheme();
  const C = {
    bg: colors.background,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    muted: AC.textMuted,
    blue: AC.indigoText || AC.primary,
    cyan: AC.infoText || AC.cyan || AC.primary,
    emerald: AC.successText,
    amber: AC.warning,
    rose: AC.error,
    soft: AC.bgSoft || AC.cardMuted || AC.bg,
    ink: AC.text,
    surface: AC.card,
    surfaceAlt: AC.bgSoft || AC.cardMuted || AC.bg,
    surfaceEmphasis: AC.primarySoft,
    dangerBg: AC.errorSoft,
    dangerBorder: AC.error,
    actionBg: AC.primary,
    actionText: AC.primaryText,
  };

  const [range, setRange] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [routeHealth, setRouteHealth] = useState(null);
  const [enterpriseStatus, setEnterpriseStatus] = useState(null);
  const [liveServices, setLiveServices] = useState(null);

  const load = useCallback(async () => {
    try {
      setError('');
      const [analyticsRes, routeRes, enterpriseRes, liveRes] = await Promise.all([
        api.get('/ai-learn/admin/certificate-analytics', { params: { range } }),
        api.get('/admin/platform-perf/route-health'),
        api.get('/admin/platform-health/enterprise-standard/status'),
        api.get('/admin/platform-health/live-services'),
      ]);
      setData(analyticsRes.data || null);
      setRouteHealth(routeRes.data || null);
      setEnterpriseStatus(enterpriseRes.data || null);
      setLiveServices(liveRes.data || null);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Unable to load certificate analytics.');
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => { void load(); }, [load]);
  useAutoRefresh(load, { intervalMs: 40000 });

  const summary = data?.summary || {};
  const funnel = Array.isArray(data?.funnel) ? data.funnel : [];
  const shareBreakdown = Array.isArray(data?.share_breakdown) ? data.share_breakdown : [];
  const statusMix = Array.isArray(data?.status_mix) ? data.status_mix : [];
  const topCourses = Array.isArray(data?.top_courses) ? data.top_courses : [];
  const recommendations = data?.executive_report?.recommended_actions || [];

  const healthCards = useMemo(() => ([
    {
      key: 'route-integrity',
      label: 'Protected route integrity',
      value: formatPct(routeHealth?.summary?.protected_integrity_pct || 100),
      color: colors.successText,
      icon: 'shield-checkmark',
    },
    {
      key: 'enterprise-score',
      label: 'Enterprise health score',
      value: String(enterpriseStatus?.platform?.latest_scan?.score ?? '--'),
      color: C.blue,
      icon: 'pulse',
    },
    {
      key: 'notifications',
      label: 'Realtime notifications today',
      value: String(liveServices?.notifications?.today ?? 0),
      color: colors.warningText,
      icon: 'notifications',
    },
    {
      key: 'realtime',
      label: 'Realtime connect success',
      value: `${Number(liveServices?.realtime?.connect_success_rate_30m || 100).toFixed(1)}%`,
      color: C.cyan,
      icon: 'git-network',
    },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ]), [enterpriseStatus?.platform?.latest_scan?.score, liveServices?.notifications?.today, liveServices?.realtime?.connect_success_rate_30m, routeHealth?.summary?.protected_integrity_pct]);

  if (loading && !data) {
    return (
      <View style={{ paddingVertical: 64, alignItems: 'center' }} data-testid="admin-certificate-analytics-loading" testID="admin-certificate-analytics-loading">
        <ActivityIndicator size="large" color={C.blue} />
        <Text style={{ color: C.muted, fontSize: 12, marginTop: 10 }}>{tx('admin.certificateAnalyticsPanel.auto.text.001', 'Loading executive certificate analytics...')}</Text>
      </View>
    );
  }

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }} data-testid="admin-certificate-analytics-panel" testID="admin-certificate-analytics-panel">
      <View style={{ backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 16 }} data-testid="admin-certificate-analytics-hero" testID="admin-certificate-analytics-hero">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <View style={{ maxWidth: 960 }}>
            <Text style={{ color: C.blue, fontSize: 11, fontWeight: '800', letterSpacing: 1.5 }} data-testid="admin-certificate-analytics-overline" testID="admin-certificate-analytics-overline">{tx('admin.certificateAnalyticsPanel.auto.text.002', 'CERTIFICATE ANALYTICS')}</Text>
            <Text style={{ color: C.text, fontSize: 28, fontWeight: '900', marginTop: 8 }} data-testid="admin-certificate-analytics-title" testID="admin-certificate-analytics-title">{tx('admin.certificateAnalyticsPanel.auto.text.003', 'Completion-to-share conversion, built for executive review.')}</Text>
            <Text style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 20 }} data-testid="admin-certificate-analytics-subtitle" testID="admin-certificate-analytics-subtitle">{tx('admin.certificateAnalyticsPanel.auto.text.004', 'Track course completions, certificate issuance, verifier opens, and share actions in one executive-grade funnel with live platform-health context.')}</Text>
          </View>

          <TouchableOpacity onPress={() => void load()} style={{ backgroundColor: C.actionBg, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8 }} data-testid="admin-certificate-analytics-refresh-button" testID="admin-certificate-analytics-refresh-button">
            <Text style={{ color: C.actionText, fontSize: 11, fontWeight: '800' }}>{tx('admin.certificateAnalyticsPanel.auto.text.005', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        <View style={{ marginTop: 14, flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} data-testid="admin-certificate-analytics-range-options" testID="admin-certificate-analytics-range-options">
          {RANGE_OPTIONS.map((option) => (
            <TouchableOpacity key={option} onPress={() => setRange(option)} style={{ backgroundColor: range === option ? C.blue : C.surfaceAlt, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: C.border }} data-testid={`admin-certificate-analytics-range-${option}`} testID={`admin-certificate-analytics-range-${option}`}>
              <Text style={{ color: range === option ? C.actionText : C.text, fontSize: 10, fontWeight: '800' }}>{option.toUpperCase()}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {error ? (
          <View style={{ marginTop: 12, backgroundColor: C.dangerBg, borderWidth: 1, borderColor: C.dangerBorder, borderRadius: 12, padding: 12 }} data-testid="admin-certificate-analytics-error" testID="admin-certificate-analytics-error">
            <Text style={{ color: C.error, fontSize: 11, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="admin-certificate-analytics-kpis" testID="admin-certificate-analytics-kpis">
        {[
          { key: 'completions', label: 'Course completions', value: summary.completed_enrollments || 0, color: C.blue },
          { key: 'issued', label: 'Certificates issued', value: summary.certificates_issued || 0, color: C.cyan },
          { key: 'views', label: 'Verifier opens', value: summary.certificates_viewed || 0, color: C.successText },
          { key: 'shares', label: 'Share actions', value: summary.certificates_shared || 0, color: C.warningText },
          { key: 'completion-share', label: 'Completion → Share', value: formatPct(summary.completion_to_share_pct), color: C.ink },
          { key: 'issue-share', label: 'Issue → Share', value: formatPct(summary.issue_to_share_pct), color: C.error },
        ].map((card) => (
          <View key={card.key} style={{ flex: 1, minWidth: 180, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid={`admin-certificate-analytics-kpi-${card.key}`} testID={`admin-certificate-analytics-kpi-${card.key}`}>
            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
            <Text style={{ color: card.color, fontSize: 25, fontWeight: '900', marginTop: 8 }} data-testid={`admin-certificate-analytics-kpi-${card.key}-value`} testID={`admin-certificate-analytics-kpi-${card.key}-value`}>{String(card.value)}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }} data-testid="admin-certificate-analytics-health-row" testID="admin-certificate-analytics-health-row">
        {healthCards.map((card) => (
          <View key={card.key} style={{ flex: 1, minWidth: 180, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid={`admin-certificate-analytics-health-${card.key}`} testID={`admin-certificate-analytics-health-${card.key}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name={card.icon} size={14} color={card.color} />
              <Text style={{ color: C.muted, fontSize: 10, fontWeight: '700' }}>{card.label}</Text>
            </View>
            <Text style={{ color: card.color, fontSize: 21, fontWeight: '900', marginTop: 8 }} data-testid={`admin-certificate-analytics-health-${card.key}-value`} testID={`admin-certificate-analytics-health-${card.key}-value`}>{card.value}</Text>
          </View>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 320, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid="admin-certificate-analytics-funnel-card" testID="admin-certificate-analytics-funnel-card">
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="admin-certificate-analytics-funnel-title" testID="admin-certificate-analytics-funnel-title">{tx('admin.certificateAnalyticsPanel.auto.text.006', 'Executive funnel')}</Text>
          <View style={{ marginTop: 12, gap: 10 }}>
            {funnel.map((step, index) => {
              const base = Number(funnel[0]?.value || 1);
              const previous = Number(index === 0 ? step.value : funnel[index - 1]?.value || 1);
              const widthPct = Math.max(12, Math.round((Number(step?.value || 0) / Math.max(base, 1)) * 100));
              return (
                <View key={step.id} data-testid={`admin-certificate-analytics-funnel-step-${step.id}`} testID={`admin-certificate-analytics-funnel-step-${step.id}`}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{step.label}</Text>
                    <Text style={{ color: C.muted, fontSize: 10 }}>{step.value} · {funnelRatio(step.value, previous)}</Text>
                  </View>
                  <View style={{ marginTop: 6, height: 12, backgroundColor: C.surfaceAlt, borderRadius: 999 }}>
                    <View style={{ width: `${widthPct}%`, height: 12, borderRadius: 999, backgroundColor: index === 0 ? C.blue : index === 1 ? C.cyan : index === 2 ? C.success : C.warning }} />
                  </View>
                </View>
              );
            })}
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 320, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid="admin-certificate-analytics-share-breakdown-card" testID="admin-certificate-analytics-share-breakdown-card">
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="admin-certificate-analytics-share-breakdown-title" testID="admin-certificate-analytics-share-breakdown-title">{tx('admin.certificateAnalyticsPanel.auto.text.007', 'Share channel breakdown')}</Text>
          <View style={{ marginTop: 12, gap: 10 }}>
            {shareBreakdown.map((item, index) => (
              <View key={`${item.event_type}-${index}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 10, backgroundColor: C.surfaceAlt }} data-testid={`admin-certificate-analytics-share-breakdown-${index}`} testID={`admin-certificate-analytics-share-breakdown-${index}`}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{formatLabel(item.event_type)}</Text>
                <Text style={{ color: C.blue, fontSize: 14, fontWeight: '900' }} data-testid={`admin-certificate-analytics-share-breakdown-${index}-value`} testID={`admin-certificate-analytics-share-breakdown-${index}-value`}>{item.count}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flex: 1, minWidth: 320, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid="admin-certificate-analytics-top-courses-card" testID="admin-certificate-analytics-top-courses-card">
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="admin-certificate-analytics-top-courses-title" testID="admin-certificate-analytics-top-courses-title">{tx('admin.certificateAnalyticsPanel.auto.text.008', 'Top certificate tracks')}</Text>
          <View style={{ marginTop: 12, gap: 8 }}>
            {topCourses.map((course, index) => (
              <View key={course.course_id || index} style={{ borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 10, backgroundColor: index === 0 ? C.surfaceEmphasis : C.surface }} data-testid={`admin-certificate-analytics-course-row-${index}`} testID={`admin-certificate-analytics-course-row-${index}`}>
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid={`admin-certificate-analytics-course-row-${index}-title`} testID={`admin-certificate-analytics-course-row-${index}-title`}>{course.course_title}</Text>
                <Text style={{ color: C.muted, fontSize: 10, marginTop: 4 }}>
                  Completions {course.completions} · Issued {course.certificates_issued} · Viewed {course.certificates_viewed} · Shared {course.certificates_shared}
                </Text>
                <Text style={{ color: C.blue, fontSize: 10, marginTop: 4, fontWeight: '700' }} data-testid={`admin-certificate-analytics-course-row-${index}-conversion`} testID={`admin-certificate-analytics-course-row-${index}-conversion`}>
                  Completion → Share {formatPct(course.completion_to_share_pct)} · Issue → Share {formatPct(course.issue_to_share_pct)}
                </Text>
              </View>
            ))}
          </View>
        </View>

        <View style={{ flex: 1, minWidth: 320, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid="admin-certificate-analytics-status-mix-card" testID="admin-certificate-analytics-status-mix-card">
          <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="admin-certificate-analytics-status-mix-title" testID="admin-certificate-analytics-status-mix-title">{tx('admin.certificateAnalyticsPanel.auto.text.009', 'Certificate status mix')}</Text>
          <View style={{ marginTop: 12, gap: 8 }}>
            {statusMix.map((row, index) => (
              <View key={`${row.status}-${index}`} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 10, backgroundColor: C.surfaceAlt }} data-testid={`admin-certificate-analytics-status-row-${index}`} testID={`admin-certificate-analytics-status-row-${index}`}>
                <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{formatLabel(row.status)}</Text>
                <Text style={{ color: row.status === 'revoked' ? C.error : row.status === 'expired' ? C.warning : row.status === 'valid' ? C.success : C.ink, fontSize: 15, fontWeight: '900' }} data-testid={`admin-certificate-analytics-status-row-${index}-value`} testID={`admin-certificate-analytics-status-row-${index}-value`}>
                  {row.count}
                </Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      <View style={{ backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 }} data-testid="admin-certificate-analytics-executive-report" testID="admin-certificate-analytics-executive-report">
        <Text style={{ color: C.text, fontSize: 14, fontWeight: '800' }} data-testid="admin-certificate-analytics-executive-report-title" testID="admin-certificate-analytics-executive-report-title">{tx('admin.certificateAnalyticsPanel.auto.text.010', 'Executive report')}</Text>
        <Text style={{ color: C.text, fontSize: 13, fontWeight: '700', marginTop: 10 }} data-testid="admin-certificate-analytics-executive-headline" testID="admin-certificate-analytics-executive-headline">
          {data?.executive_report?.headline || 'No executive summary available yet.'}
        </Text>
        <View style={{ marginTop: 12, gap: 8 }}>
          {recommendations.map((item, index) => (
            <View key={`${item}-${index}`} style={{ flexDirection: 'row', gap: 8, alignItems: 'flex-start' }} data-testid={`admin-certificate-analytics-recommendation-${index}`} testID={`admin-certificate-analytics-recommendation-${index}`}>
              <Ionicons name="sparkles" size={14} color={C.blue} style={{ marginTop: 2 }} />
              <Text style={{ color: C.muted, fontSize: 11, lineHeight: 18, flex: 1 }}>{item}</Text>
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}