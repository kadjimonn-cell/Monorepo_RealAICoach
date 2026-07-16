import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, Platform } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { handleAppRecoverableError } from '../../utils/appRecoverableError';
function makeT(AC: any) { return {
  bg: AC.bg, bgSoft: AC.card, card: 'var(--app-card-bg)', cardHover: AC.surfaceHover,
  border: 'var(--app-border)', text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', primarySoft: 'var(--app-primary-soft)' as any, success: 'var(--app-success)' as any, successSoft: 'var(--app-success-soft)' as any,
  warning: 'var(--app-warning)' as any, warningSoft: 'var(--app-warning-soft)' as any, error: 'var(--app-error)' as any, errorSoft: 'var(--app-error-soft)' as any,
  purple: 'var(--app-primary)', purpleSoft: 'var(--app-primary-soft)', cyan: 'var(--app-primary)', cyanSoft: 'var(--app-primary-soft)',
  gold: 'var(--app-primary)', goldSoft: 'var(--app-primary-soft)',
}; }

// Module-scope fallback for KPICard/MetricItem/MetricCard helpers (can't access component-scoped T)
const T = {
  bg: 'var(--app-bg)' as any, bgSoft: 'var(--app-surface)' as any, card: 'var(--app-card-bg)' as any, cardHover: 'var(--app-card-muted)' as any,
  border: 'var(--app-border)' as any, text: 'var(--app-text)' as any, textSec: 'var(--app-text-sec)' as any, textMuted: 'var(--app-text-muted)' as any,
  primary: 'var(--app-primary)' as any, primarySoft: 'var(--app-primary-soft)' as any, success: 'var(--app-success)' as any, successSoft: 'var(--app-success-soft)' as any,
  warning: 'var(--app-warning)' as any, warningSoft: 'var(--app-warning-soft)' as any, error: 'var(--app-error)' as any, errorSoft: 'var(--app-error-soft)' as any,
  purple: 'var(--app-primary)', purpleSoft: 'var(--app-primary-soft)', cyan: 'var(--app-primary)', cyanSoft: 'var(--app-primary-soft)',
  gold: 'var(--app-primary)', goldSoft: 'var(--app-primary-soft)',
  successText: 'var(--app-success)', warningText: 'var(--app-warning)', purpleText: 'var(--app-primary)',
};

interface Props { colors: any; }

export default function HiringAnalyticsPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data: exec, loading: exLoading, refetch: load } = useLiveQuery('/hiring-analytics/executive', { entity: 'hiring', pollInterval: 60000 });
  const { data: trendsData, loading: trLoading } = useLiveQuery('/hiring-analytics/trends', { entity: 'hiring', pollInterval: 60000 });
  const { data: roi, loading: roLoading } = useLiveQuery('/hiring-analytics/roi', { entity: 'hiring', pollInterval: 60000 });
  const { data: reportSettings, loading: rsLoading } = useLiveQuery('/hiring-reports/settings', { entity: 'hiring', pollInterval: 60000 });
  const trends = trendsData?.trends || [];
  const loading = exLoading || trLoading || roLoading || rsLoading;
  const [section, setSection] = useState<'overview' | 'funnel' | 'ai' | 'roi' | 'trends'>('overview');
  const [sendingReport, setSendingReport] = useState(false);

  const downloadCSV = async () => {
    const backendUrl = typeof window !== 'undefined' && (`https://${window.location.host}`) ? (`https://${window.location.host}`) : (process.env.REACT_APP_BACKEND_URL || '');
    const token = typeof localStorage !== 'undefined' ? localStorage.getItem('session_token') : '';
    const url = `${backendUrl}/api/hiring-analytics/export/csv`;
    if (Platform.OS === 'web') {
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `hiring_analytics_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
      } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/HiringAnalyticsPanel.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
    }
  };

  if (loading) return (
    <View style={{ paddingVertical: 60, alignItems: 'center' }}>
      <AutoFixBanner domain="hiring" />
      <ActivityIndicator size="large" color={T.primary} />
      <Text style={{ color: T.textMuted, marginTop: 16, fontSize: 14, letterSpacing: 1 }}>{tx('admin.hiringAnalyticsPanel.auto.text.001', 'COMPILING EXECUTIVE REPORT...')}</Text>
    </View>
  );

  if (!exec) return null;
  const kpi = exec.kpi || {};
  const funnel = exec.hiring_funnel || {};
  const eff = exec.efficiency || {};
  const aiP = exec.ai_performance || {};
  const fair = exec.fairness || {};
  const cx = exec.candidate_experience || {};
  const stageMap = exec.pipeline_stages || {};
  const decMap = exec.decision_distribution || {};
  const ivStatus = exec.interview_status || {};

  const sections = [
    { id: 'overview', label: 'Overview', icon: 'grid-outline' },
    { id: 'funnel', label: 'Funnel', icon: 'funnel-outline' },
    { id: 'ai', label: 'AI Performance', icon: 'flash-outline' },
    { id: 'roi', label: 'ROI', icon: 'trending-up-outline' },
    { id: 'trends', label: 'Trends', icon: 'analytics-outline' },
  ];

  return (
    <View data-testid="hiring-analytics-panel" testID="hiring-analytics-panel">
      {/* Header */}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <View>
          <Text style={{ color: T.gold, fontSize: 11, fontWeight: '800', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 4 }}>{tx('admin.hiringAnalyticsPanel.auto.text.002', 'HIRING INTELLIGENCE')}</Text>
          <Text style={{ color: T.text, fontSize: 22, fontWeight: '800' }}>{tx('admin.hiringAnalyticsPanel.auto.text.003', 'Executive Analytics')}</Text>
        </View>
        <TouchableOpacity data-testid="export-csv-btn" testID="export-csv-btn" onPress={downloadCSV}
          style={{
            flexDirection: 'row', alignItems: 'center', gap: 6,
            paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10,
            backgroundColor: (globalThis as any).__alphaColor(T.gold, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.gold, '44'),
          }}>
          <Ionicons name="download-outline" size={16} color={T.gold} />
          <Text style={{ color: T.gold, fontSize: 12, fontWeight: '700' }}>{tx('admin.hiringAnalyticsPanel.auto.text.004', 'Export CSV')}</Text>
        </TouchableOpacity>
      </View>

      {/* Section Nav */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', gap: 6 }}>
          {sections.map(s => (
            <TouchableOpacity key={s.id} data-testid={`analytics-section-${s.id}`} testID={`analytics-section-${s.id}`}
              onPress={() => setSection(s.id as any)}
              style={{
                flexDirection: 'row', alignItems: 'center', gap: 5,
                paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10,
                backgroundColor: section === s.id ? T.primary : T.card,
                borderWidth: 1, borderColor: section === s.id ? T.primary : T.border,
              }}>
              <Ionicons name={s.icon as any} size={14} color={section === s.id ? 'var(--app-primary-text)' : T.textMuted} />
              <Text style={{ color: section === s.id ? 'var(--app-primary-text)' : T.textMuted, fontSize: 12, fontWeight: '700' }}>{s.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>

      {/* OVERVIEW */}
      {section === 'overview' && (
        <View>
          {/* KPI Grid */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
            <KPICard label="Active Pipelines" value={kpi.total_pipelines} delta={kpi.new_pipelines_30d} deltaLabel="30d" color={T.primary} />
            <KPICard label="Total Interviews" value={kpi.total_interviews} delta={kpi.new_interviews_30d} deltaLabel="30d" color={T.purpleText} />
            <KPICard label="Applications" value={kpi.total_applications} delta={kpi.new_applications_30d} deltaLabel="30d" color={T.cyan} />
            <KPICard label="Active Jobs" value={kpi.active_jobs} color={T.successText} />
            <KPICard label="AI Summaries" value={kpi.ai_summaries_generated} color={T.gold} />
            <KPICard label="Conversion" value={`${funnel.conversion_rate}%`} color={T.successText} />
          </View>

          {/* Efficiency Row */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 12, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.005', 'EFFICIENCY METRICS')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 20 }}>
              <MetricItem label="Avg Time-to-Fill" value={eff.avg_time_to_fill_days ? `${eff.avg_time_to_fill_days}d` : 'N/A'} color={T.primary} />
              <MetricItem label="Avg AI Confidence" value={`${eff.avg_confidence || 0}%`} color={T.purpleText} />
              <MetricItem label="Interview Completion" value={`${eff.interview_completion_rate || 0}%`} color={T.successText} />
              <MetricItem label="Video Hours" value={`${eff.total_video_hours || 0}h`} color={T.cyan} />
            </View>
          </View>

          {/* Candidate Experience + Fairness */}
          <View style={{ flexDirection: 'row', gap: 10, marginBottom: 12 }}>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.006', 'CANDIDATE EXPERIENCE')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
                <Text style={{ color: T.gold, fontSize: 28, fontWeight: '800' }}>{cx.avg_rating || '-'}</Text>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>/5</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{cx.total_ratings} ratings | {cx.recommend_pct || 0}% recommend</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.007', 'FAIRNESS')}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4 }}>
                <Text style={{ color: fair.pending_flags > 0 ? T.warning : T.success, fontSize: 28, fontWeight: '800' }}>{fair.pending_flags}</Text>
                <Text style={{ color: T.textMuted, fontSize: 12 }}>{tx('admin.hiringAnalyticsPanel.auto.text.008', 'pending')}</Text>
              </View>
              <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 4 }}>{fair.total_flags} total | {fair.reviewed} reviewed</Text>
            </View>
          </View>
        </View>
      )}

      {/* FUNNEL */}
      {section === 'funnel' && (
        <View>
          {/* Funnel Bars */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 16, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.009', 'HIRING FUNNEL')}</Text>
            {['applications', 'screened', 'interviewed', 'offered'].map((stage, i) => {
              const val = (funnel as any)[stage] || 0;
              const maxVal = Math.max(funnel.applications || 1, 1);
              // eslint-disable-next-line @typescript-eslint/no-unused-vars
              const _pct = Math.round(val / maxVal * 100);
              const colors = [T.primary, T.purple, T.cyan, T.success];
              return (
                <View key={stage} style={{ marginBottom: 14 }}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 }}>
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '600', textTransform: 'capitalize' }}>{stage}</Text>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ color: colors[i], fontSize: 15, fontWeight: '800' }}>{val}</Text>
                      <Text style={{ color: T.textMuted, fontSize: 11 }}>{pct}%</Text>
                    </View>
                  </View>
                  <View style={{ height: 8, backgroundColor: T.bgSoft, borderRadius: 4 }}>
                    <View style={{ height: 8, backgroundColor: colors[i], borderRadius: 4, width: `${Math.min(pct, 100)}%` }} />
                  </View>
                </View>
              );
            })}
          </View>

          {/* Pipeline Stages */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 12, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.010', 'PIPELINE STAGE DISTRIBUTION')}</Text>
            {Object.entries(stageMap).map(([stage, count]) => (
              <View key={stage} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: T.border }}>
                <Text style={{ color: T.text, fontSize: 13, textTransform: 'capitalize' }}>{stage.replace(/_/g, ' ')}</Text>
                <Text style={{ color: T.primary, fontSize: 13, fontWeight: '700' }}>{String(count)}</Text>
              </View>
            ))}
          </View>

          {/* Interview Status */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 12, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.011', 'INTERVIEW STATUS')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
              {Object.entries(ivStatus).map(([status, count]) => {
                const sc = status === 'completed' ? T.success : status === 'cancelled' ? T.error : status === 'scheduled' ? T.primary : T.warning;
                return (
                  <View key={status} style={{ alignItems: 'center', minWidth: 65 }}>
                    <Text style={{ color: sc, fontSize: 24, fontWeight: '800' }}>{String(count)}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, textTransform: 'capitalize' }}>{status}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        </View>
      )}

      {/* AI PERFORMANCE */}
      {section === 'ai' && (
        <View>
          {/* AI Accuracy */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 12, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.012', 'AI PREDICTION ACCURACY')}</Text>
            <View style={{
              width: 90, height: 90, borderRadius: 45, borderWidth: 4,
              borderColor: aiP.accuracy != null ? (aiP.accuracy >= 70 ? T.success : aiP.accuracy >= 50 ? T.warning : T.error) : T.border,
              alignItems: 'center', justifyContent: 'center',
              backgroundColor: (globalThis as any).__alphaColor((aiP.accuracy != null ? (aiP.accuracy >= 70 ? T.success : aiP.accuracy >= 50 ? T.warning : T.error) : T.border), '15'),
            }}>
              <Text style={{
                color: aiP.accuracy != null ? (aiP.accuracy >= 70 ? T.success : aiP.accuracy >= 50 ? T.warning : T.error) : T.textMuted,
                fontSize: 28, fontWeight: '800',
              }}>{aiP.accuracy != null ? `${aiP.accuracy}%` : 'N/A'}</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 24, marginTop: 16 }}>
              <View style={{ alignItems: 'center' }}>
                <Text style={{ color: T.successText, fontSize: 20, fontWeight: '700' }}>{aiP.correct || 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.013', 'Correct')}</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text style={{ color: T.error, fontSize: 20, fontWeight: '700' }}>{aiP.incorrect || 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.014', 'Incorrect')}</Text>
              </View>
              <View style={{ alignItems: 'center' }}>
                <Text style={{ color: T.textMuted, fontSize: 20, fontWeight: '700' }}>{aiP.total_outcomes || 0}</Text>
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.015', 'Total')}</Text>
              </View>
            </View>
          </View>

          {/* Decision Distribution */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 12, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.016', 'AI DECISION DISTRIBUTION')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 16 }}>
              {Object.entries(decMap).map(([dec, count]) => {
                const dc = dec.includes('hire') && !dec.includes('no') ? T.success : dec.includes('no') ? T.error : dec === 'maybe' ? T.warning : T.textMuted;
                return (
                  <View key={dec} style={{ alignItems: 'center', minWidth: 65 }}>
                    <Text style={{ color: dc, fontSize: 26, fontWeight: '800' }}>{String(count)}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, textTransform: 'capitalize' }}>{dec.replace(/_/g, ' ')}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        </View>
      )}

      {/* ROI */}
      {section === 'roi' && roi && (
        <View>
          {/* AI Impact */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 14, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.017', 'AI IMPACT & SAVINGS')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <MetricCard label="AI Decisions Made" value={roi.ai_impact?.ai_decisions_made} color={T.purpleText} />
              <MetricCard label="Smart Scheduled" value={roi.ai_impact?.smart_scheduled} color={T.cyan} />
              <MetricCard label="Hours Saved" value={`${roi.ai_impact?.estimated_hours_saved || 0}h`} color={T.gold} />
            </View>
          </View>

          {/* Interview Efficiency */}
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, marginBottom: 12, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 14, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.018', 'INTERVIEW EFFICIENCY')}</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
              <MetricCard label="Completion Rate" value={`${roi.interview_efficiency?.completion_rate || 0}%`} color={T.successText} />
              <MetricCard label="Cancelled" value={roi.interview_efficiency?.cancelled} color={T.error} />
              <MetricCard label="No-Show" value={roi.interview_efficiency?.no_show} color={T.warningText} />
            </View>
          </View>

          {/* Video & Quality */}
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.019', 'VIDEO USAGE')}</Text>
              <Text style={{ color: T.cyan, fontSize: 26, fontWeight: '800' }}>{roi.video_usage?.total_minutes || 0}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>minutes ({roi.video_usage?.total_rooms || 0} rooms)</Text>
              <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>Avg: {roi.video_usage?.avg_session_minutes || 0}min/session</Text>
            </View>
            <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
              <Text style={{ color: T.textSec, fontSize: 10, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.020', 'HIRE QUALITY')}</Text>
              <Text style={{ color: T.gold, fontSize: 26, fontWeight: '800' }}>{roi.hire_quality?.avg_performance || 'N/A'}</Text>
              <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.hiringAnalyticsPanel.auto.text.021', '/10 performance')}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 4 }}>{roi.hire_quality?.avg_retention_months || 'N/A'} months avg retention</Text>
            </View>
          </View>
        </View>
      )}

      {/* TRENDS */}
      {section === 'trends' && (
        <View>
          <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: T.border }}>
            <Text style={{ color: T.textSec, fontSize: 11, fontWeight: '700', letterSpacing: 1.5, marginBottom: 14, textTransform: 'uppercase' }}>{tx('admin.hiringAnalyticsPanel.auto.text.022', '30-DAY HIRING ACTIVITY')}</Text>
            {/* Trend bars - last 14 days for readability */}
            {trends.slice(-14).map((day, i) => {
              const maxActivity = Math.max(...trends.slice(-14).map(d => d.pipelines + d.interviews + d.applications), 1);
              const total = day.pipelines + day.interviews + day.applications;
              // eslint-disable-next-line @typescript-eslint/no-unused-vars
              const pct = Math.round(total / maxActivity * 100);
              return (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 8 }}>
                  <Text style={{ color: T.textMuted, fontSize: 10, width: 42, textAlign: 'right' }}>{day.day_label}</Text>
                  <View style={{ flex: 1, height: 16, backgroundColor: T.bgSoft, borderRadius: 4, flexDirection: 'row', overflow: 'hidden' }}>
                    {day.applications > 0 && (
                      <View style={{ height: 16, backgroundColor: T.cyan, width: `${day.applications / maxActivity * 100}%` }} />
                    )}
                    {day.pipelines > 0 && (
                      <View style={{ height: 16, backgroundColor: T.primary, width: `${day.pipelines / maxActivity * 100}%` }} />
                    )}
                    {day.interviews > 0 && (
                      <View style={{ height: 16, backgroundColor: T.purple, width: `${day.interviews / maxActivity * 100}%` }} />
                    )}
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 10, width: 24, textAlign: 'right' }}>{total}</Text>
                </View>
              );
            })}
            {/* Legend */}
            <View style={{ flexDirection: 'row', gap: 16, marginTop: 12, justifyContent: 'center' }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.cyan }} />
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.023', 'Applications')}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.primary }} />
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.024', 'Pipelines')}</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <View style={{ width: 10, height: 10, borderRadius: 2, backgroundColor: T.purple }} />
                <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.hiringAnalyticsPanel.auto.text.025', 'Interviews')}</Text>
              </View>
            </View>
          </View>
        </View>
      )}

      {/* Weekly Report Controls */}
      <View style={{
        marginTop: 16, backgroundColor: T.card, borderRadius: 14, padding: 16,
        borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.gold, '40'), borderTopWidth: 3, borderTopColor: T.gold,
      }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <View>
            <Text style={{ color: T.gold, fontSize: 14, fontWeight: '700' }}>{tx('admin.hiringAnalyticsPanel.auto.text.026', 'Weekly Hiring Report')}</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>
              {reportSettings?.enabled !== false ? 'Scheduled every Monday at 9:30 AM UTC' : 'Currently disabled'}
            </Text>
          </View>
          <TouchableOpacity data-testid="toggle-weekly-report" testID="toggle-weekly-report"
            onPress={async () => {
              const newVal = !(reportSettings?.enabled !== false);
              await api.post('/hiring-reports/settings', { enabled: newVal });
              setReportSettings((p: any) => ({ ...p, enabled: newVal }));
            }}
            style={{
              paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8,
              backgroundColor: reportSettings?.enabled !== false ? (globalThis as any).__alphaColor(T.success, '22') : T.error + '22',
              borderWidth: 1, borderColor: reportSettings?.enabled !== false ? (globalThis as any).__alphaColor(T.success, '44') : T.error + '44',
            }}>
            <Text style={{
              color: reportSettings?.enabled !== false ? T.success : T.error,
              fontSize: 11, fontWeight: '700',
            }}>{reportSettings?.enabled !== false ? 'ENABLED' : 'DISABLED'}</Text>
          </TouchableOpacity>
        </View>
        {reportSettings?.last_report && (
          <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 8 }}>
            Last sent: {reportSettings.last_report.generated_at?.slice(0, 10)} | Delivered to {reportSettings.last_report.delivered}/{reportSettings.last_report.sent_to} admins
          </Text>
        )}
        <TouchableOpacity data-testid="send-report-now" testID="send-report-now"
          onPress={async () => {
            setSendingReport(true);
            try {
              await api.post('/hiring-reports/send-now');
              const rs = await api.get('/hiring-reports/settings');
              setReportSettings(rs.data);
            } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/HiringAnalyticsPanel.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
            setSendingReport(false);
          }}
          disabled={sendingReport}
          style={{
            padding: 10, borderRadius: 8, alignItems: 'center',
            flexDirection: 'row', justifyContent: 'center', gap: 6,
            backgroundColor: (globalThis as any).__alphaColor(T.gold, '22'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.gold, '44'),
          }}>
          <Ionicons name="send" size={14} color={T.gold} />
          <Text style={{ color: T.gold, fontSize: 12, fontWeight: '600' }}>
            {sendingReport ? 'Sending...' : 'Send Report Now'}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Refresh */}
      <TouchableOpacity data-testid="refresh-analytics" testID="refresh-analytics" onPress={load}
        style={{
          marginTop: 16, padding: 12, borderRadius: 10,
          backgroundColor: T.card, borderWidth: 1, borderColor: T.border,
          alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6,
        }}>
        <Ionicons name="refresh" size={14} color={T.textMuted} />
        <Text style={{ color: T.textMuted, fontSize: 12, fontWeight: '600' }}>{tx('admin.hiringAnalyticsPanel.auto.text.027', 'Refresh Analytics')}</Text>
      </TouchableOpacity>
    </View>
  );
}

/* ── Sub-components ── */

const tx = (_key: string, fallback: string) => fallback;

const KPICard = ({ label, value, delta, deltaLabel, color }: any) => (
  <View style={{
    backgroundColor: T.card, borderRadius: 14, padding: 16, minWidth: 150, flex: 1,
    borderWidth: 1, borderColor: T.border, borderTopWidth: 3, borderTopColor: color,
  }}>
    <Text style={{ color: T.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 6 }}>{label}</Text>
    <Text style={{ color: T.text, fontSize: 26, fontWeight: '800' }}>{value ?? 0}</Text>
    {delta != null && (
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 4 }}>
        <Ionicons name="arrow-up" size={10} color={T.successText} />
        <Text style={{ color: T.successText, fontSize: 10, fontWeight: '600' }}>+{delta} {deltaLabel}</Text>
      </View>
    )}
  </View>
);

const MetricItem = ({ label, value, color }: any) => (
  <View style={{ minWidth: 100 }}>
    <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value}</Text>
    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{label}</Text>
  </View>
);

const MetricCard = ({ label, value, color }: any) => (
  <View style={{
    flex: 1, minWidth: 100, backgroundColor: (globalThis as any).__alphaColor(color, '12'), borderRadius: 10,
    padding: 14, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(color, '30'), alignItems: 'center',
  }}>
    <Text style={{ color, fontSize: 22, fontWeight: '800' }}>{value ?? 0}</Text>
    <Text style={{ color: T.textMuted, fontSize: 10, marginTop: 2 }}>{label}</Text>
  </View>
);
