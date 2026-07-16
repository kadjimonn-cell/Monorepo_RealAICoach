import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import api from '../../services/api';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useTheme } from '../../context/ThemeContext';

const tx = (_key: string, fallback: string) => fallback;

export default function AILearningHubInsightsPanel({ colors: _colors, darkMode: darkModeProp }: { colors: any; darkMode?: boolean }) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const colors = useAdminTheme();
  const { darkMode: themeDark } = useTheme();
  const _darkMode = darkModeProp ?? themeDark;
  // Theme-driven palette — resolves from the current theme (light or dark).
  const C = {
    bg: colors.bg,
    card: colors.card,
    cardMuted: colors.surfaceHover,
    border: colors.border,
    borderSoft: colors.borderSoft || colors.border,
    text: colors.text,
    muted: colors.textMuted,
    textSoft: colors.textSec,
    blue: colors.primary,
    cyan: colors.accent,
    emerald: colors.success,
    amber: colors.warning,
    error: colors.error,
    softInfoBg: colors.primarySoft,
    softInfoBorder: colors.primarySoft,
    actionBg: colors.primary,
    actionText: colors.primaryText || colors.text,
  };

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [data, setData] = useState<any>(null);

  const completion = Number(data?.overview?.completion_rate_pct || 0);
  const anchoredRatio = Number(data?.overview?.anchored_certificate_ratio_pct || 0);

  const load = useCallback(async () => {
    try {
      setError('');
      const r = await api.get('/ai-learn/admin/executive-insights');
      setData(r.data || null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Unable to load AI Learning Hub executive insights.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useAutoRefresh(load, { intervalMs: 30000 });

  return (
    <View style={{ flex: 1, padding: 16 }} data-testid="admin-ai-learning-hub-insights-panel" testID="admin-ai-learning-hub-insights-panel">
      <View style={{ backgroundColor: C.card, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 12, padding: 14 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <View>
            <Text style={{ color: C.text, fontSize: 17, fontWeight: '900' }} data-testid="admin-ai-learning-hub-insights-title" testID="admin-ai-learning-hub-insights-title">{tx('admin.aILearningHubInsightsPanel.auto.text.001', 'AI Learning Hub Insights')}</Text>
            <Text style={{ color: C.muted, fontSize: 11, marginTop: 2 }} data-testid="admin-ai-learning-hub-insights-subtitle" testID="admin-ai-learning-hub-insights-subtitle">{tx('admin.aILearningHubInsightsPanel.auto.text.002', 'View-only executive telemetry for autonomous learning operations and trust-led certificate lifecycle.')}</Text>
          </View>
          <TouchableOpacity onPress={load} style={{ backgroundColor: C.actionBg, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: C.softInfoBorder }} data-testid="admin-ai-learning-hub-insights-refresh-button" testID="admin-ai-learning-hub-insights-refresh-button">
            <Text style={{ color: C.actionText, fontSize: 11, fontWeight: '700' }}>{tx('admin.aILearningHubInsightsPanel.auto.text.003', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>

        {error ? (
          <View style={{ backgroundColor: (globalThis as any).__alphaColor(C.error, '18'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '55'), borderRadius: 10, padding: 10 }} data-testid="admin-ai-learning-hub-insights-error" testID="admin-ai-learning-hub-insights-error">
            <Text style={{ color: C.error, fontSize: 12, fontWeight: '700' }}>{error}</Text>
          </View>
        ) : null}

        {loading ? (
          <Text style={{ color: C.muted, fontSize: 12 }} data-testid="admin-ai-learning-hub-insights-loading" testID="admin-ai-learning-hub-insights-loading">{tx('admin.aILearningHubInsightsPanel.auto.text.004', 'Loading AI Learning Hub analytics...')}</Text>
        ) : null}

        {!loading && data ? (
          <>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 }} data-testid="admin-ai-learning-hub-insights-kpis" testID="admin-ai-learning-hub-insights-kpis">
              {[
                { key: 'courses', label: 'Total Courses', value: data?.overview?.total_courses ?? 0, color: C.blue, icon: 'school' },
                { key: 'enrollments', label: 'Enrollments', value: data?.overview?.total_enrollments ?? 0, color: C.cyan, icon: 'layers' },
                { key: 'completion', label: 'Completion Rate', value: `${Number(data?.overview?.completion_rate_pct || 0).toFixed(1)}%`, color: C.emerald, icon: 'checkmark-circle' },
                { key: 'weekly', label: 'Weekly Learning Minutes', value: data?.overview?.weekly_learning_minutes ?? 0, color: C.amber, icon: 'time' },
                { key: 'anchored', label: 'Anchored Certificates', value: data?.overview?.anchored_certificates ?? 0, color: C.blue, icon: 'shield-checkmark' },
                { key: 'pending-anchor', label: 'Pending Anchors', value: data?.overview?.pending_anchor_count ?? 0, color: C.amber, icon: 'git-network' },
                { key: 'video-alignment', label: 'Video Topic Match', value: `${Number(data?.overview?.video_topic_alignment_pct || 0).toFixed(1)}%`, color: C.cyan, icon: 'videocam' },
              ].map((kpi) => (
                <View key={kpi.key} style={{ flex: 1, minWidth: 180, backgroundColor: C.cardMuted, borderRadius: 10, borderWidth: 1, borderColor: C.borderSoft, padding: 10 }} data-testid={`admin-ai-learning-hub-kpi-${kpi.key}`} testID={`admin-ai-learning-hub-kpi-${kpi.key}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={kpi.icon as any} size={13} color={kpi.color} />
                    <Text style={{ color: C.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase' }}>{kpi.label}</Text>
                  </View>
                  <Text style={{ color: kpi.color, fontSize: 21, fontWeight: '900', marginTop: 6 }} data-testid={`admin-ai-learning-hub-kpi-${kpi.key}-value`} testID={`admin-ai-learning-hub-kpi-${kpi.key}-value`}>{String(kpi.value)}</Text>
                </View>
              ))}
            </View>

            <View style={{ marginTop: 10, borderWidth: 1, borderColor: C.borderSoft, borderRadius: 10, padding: 10, backgroundColor: C.cardMuted }} data-testid="admin-ai-learning-hub-score-bars" testID="admin-ai-learning-hub-score-bars">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="admin-ai-learning-hub-score-bars-title" testID="admin-ai-learning-hub-score-bars-title">{tx('admin.aILearningHubInsightsPanel.auto.text.005', 'Execution Quality Gauges')}</Text>

              <View style={{ marginTop: 8 }} data-testid="admin-ai-learning-hub-completion-gauge" testID="admin-ai-learning-hub-completion-gauge">
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '700' }}>{tx('admin.aILearningHubInsightsPanel.auto.text.006', 'Completion health')}</Text>
                  <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '700' }} data-testid="admin-ai-learning-hub-completion-gauge-value" testID="admin-ai-learning-hub-completion-gauge-value">{completion.toFixed(1)}%</Text>
                </View>
                <View style={{ marginTop: 4, height: 8, borderRadius: 999, backgroundColor: C.borderSoft }}>
                  <View style={{ height: 8, borderRadius: 999, width: `${Math.max(0, Math.min(100, completion))}%`, backgroundColor: C.success }} />
                </View>
              </View>

              <View style={{ marginTop: 10 }} data-testid="admin-ai-learning-hub-anchor-gauge" testID="admin-ai-learning-hub-anchor-gauge">
                <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                  <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '700' }}>{tx('admin.aILearningHubInsightsPanel.auto.text.007', 'Anchoring coverage')}</Text>
                  <Text style={{ color: C.textSoft, fontSize: 10, fontWeight: '700' }} data-testid="admin-ai-learning-hub-anchor-gauge-value" testID="admin-ai-learning-hub-anchor-gauge-value">{anchoredRatio.toFixed(1)}%</Text>
                </View>
                <View style={{ marginTop: 4, height: 8, borderRadius: 999, backgroundColor: C.borderSoft }}>
                  <View style={{ height: 8, borderRadius: 999, width: `${Math.max(0, Math.min(100, anchoredRatio))}%`, backgroundColor: C.blue }} />
                </View>
              </View>
            </View>

            <View style={{ marginTop: 10, backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.borderSoft, padding: 10 }} data-testid="admin-ai-learning-hub-optimization-report" testID="admin-ai-learning-hub-optimization-report">
              <Text style={{ color: C.text, fontSize: 12, fontWeight: '900' }} data-testid="admin-ai-learning-hub-optimization-report-title" testID="admin-ai-learning-hub-optimization-report-title">{tx('admin.aILearningHubInsightsPanel.auto.text.008', 'AI Optimization Report')}</Text>
              {(data?.optimization_report?.focus || []).map((focus: string, i: number) => (
                <Text key={`${focus}-${i}`} style={{ color: C.textSoft, marginTop: 5, fontSize: 11 }} data-testid={`admin-ai-learning-hub-optimization-focus-${i}`} testID={`admin-ai-learning-hub-optimization-focus-${i}`}>• {focus}</Text>
              ))}

              {(data?.optimization_report?.suggested_actions || []).map((action: string, i: number) => (
                <View key={`${action}-${i}`} style={{ marginTop: 6, borderWidth: 1, borderColor: C.softInfoBorder, borderRadius: 8, padding: 8, backgroundColor: C.softInfoBg }} data-testid={`admin-ai-learning-hub-optimization-action-${i}`} testID={`admin-ai-learning-hub-optimization-action-${i}`}>
                  <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{action}</Text>
                </View>
              ))}
            </View>
          </>
        ) : null}
      </View>
    </View>
  );
}
