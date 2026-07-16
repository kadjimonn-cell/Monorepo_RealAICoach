import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';

// Theme adapter — maps the v2 admin theme shape onto the short-name palette
// that this panel historically used. This is the same pattern applied in
// AccessibilityPanel / CodeHealthPanel so theme changes propagate through
// React state rather than relying purely on CSS variable re-resolution.
function makeC(AC: any) {
  return {
    bg: AC.bg,
    surface: AC.card,
    surfaceHover: AC.surfaceHover,
    border: AC.border,
    text: AC.text,
    muted: AC.textMuted,
    primary: AC.primary,
    success: AC.success,
    successText: AC.successText,
    warning: AC.warning,
    warningText: AC.warningText,
    error: AC.error,
    primaryText: AC.primaryText || AC.text,
    emerald: AC.success,
    amber: AC.warning,
    rose: AC.error,
    violet: AC.accent || AC.primary,
  };
}

const tx = (_key: string, fallback: string) => fallback;

function GradeChip({ grade }: { grade: string }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const colors: Record<string, string> = { A: C.success, B: C.primary, C: C.warning, D: C.warningText, F: C.error };
  const color = colors[grade] || C.muted;
  return (
    <View style={{ backgroundColor: `${color}20`, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3, borderWidth: 1, borderColor: `${color}40`, minWidth: 28, alignItems: 'center' }}>
      <Text style={{ color, fontSize: 12, fontWeight: '800' }}>{grade}</Text>
    </View>
  );
}

function FrictionBar({ score }: { score: number }) {
  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const color = score < 10 ? C.success : score < 25 ? C.primary : score < 50 ? C.warning : score < 75 ? C.warningText : C.error;
  return (
    <View style={{ width: 80, height: 6, backgroundColor: C.surfaceHover, borderRadius: 3, overflow: 'hidden' }}>
      <View style={{ width: `${Math.min(score, 100)}%`, height: '100%', backgroundColor: color, borderRadius: 3 }} />
    </View>
  );
}

export default function FeedbackHeatmapPanel() {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const C = React.useMemo(() => makeC(AC), [AC]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(7);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const res = await api.get(`/admin/executive/feedback-heatmap?days=${days}`);
      setData(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator color={C.primary} size="large" /></View>;
  if (error) return <View style={{ padding: 20 }}><Text style={{ color: C.error }}>{error}</Text></View>;
  if (!data) return null;

  const { summary, heatmap, top_friction_routes } = data;
  const dayOptions = [7, 14, 30, 90];

  return (
    <View style={{ flex: 1 }} data-testid="feedback-heatmap-panel" testID="feedback-heatmap-panel">
      {/* Period Selector */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <Text style={{ color: C.muted, fontSize: 12, fontWeight: '600' }}>{tx('admin.feedbackHeatmapPanel.auto.text.001', 'Period:')}</Text>
        {dayOptions.map(d => (
          <TouchableOpacity key={d} onPress={() => setDays(d)} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: days === d ? C.primary : C.surfaceHover, borderWidth: 1, borderColor: days === d ? C.primary : C.border }} data-testid={`heatmap-period-${d}`} testID={`heatmap-period-${d}`}>
            <Text style={{ color: days === d ? C.primaryText : C.text, fontSize: 12, fontWeight: '600' }}>{d}d</Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity onPress={load} style={{ marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, backgroundColor: C.surfaceHover, borderWidth: 1, borderColor: C.border }} data-testid="heatmap-refresh-btn" testID="heatmap-refresh-btn">
          <Ionicons name="refresh" size={12} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 11, fontWeight: '600' }}>{tx('admin.feedbackHeatmapPanel.auto.text.002', 'Refresh')}</Text>
        </TouchableOpacity>
      </View>

      {/* Summary KPIs */}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Routes Analyzed', value: data.total_routes, color: C.primary },
          { label: 'Avg Friction', value: summary.avg_friction, color: summary.avg_friction < 25 ? C.success : C.warning },
          { label: 'Grade A Routes', value: summary.routes_grade_a, color: C.successText },
          { label: 'Grade F Routes', value: summary.routes_grade_f, color: summary.routes_grade_f > 0 ? C.error : C.success },
          { label: 'Total Errors', value: summary.total_errors, color: summary.total_errors > 0 ? C.error : C.success },
          { label: 'Support Tickets', value: summary.total_support_tickets, color: summary.total_support_tickets > 5 ? C.warning : C.muted },
        ].map((kpi, i) => (
          <View key={i} style={{ flex: 1, minWidth: 120, backgroundColor: C.surface, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid={`heatmap-kpi-${i}`} testID={`heatmap-kpi-${i}`}>
            <Text style={{ color: C.muted, fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>{kpi.label}</Text>
            <Text style={{ color: kpi.color, fontSize: 20, fontWeight: '800' }}>{kpi.value}</Text>
          </View>
        ))}
      </View>

      {/* Top Friction Routes */}
      {top_friction_routes.length > 0 && (
        <View style={{ marginBottom: 20 }}>
          <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 12 }}>{tx('admin.feedbackHeatmapPanel.auto.text.003', 'Friction Leaderboard')}</Text>
          <View style={{ gap: 6 }}>
            {top_friction_routes.map((r: any, i: number) => (
              <View key={r.route} style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: C.surface, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border, gap: 10 }} data-testid={`friction-route-${i}`} testID={`friction-route-${i}`}>
                <Text style={{ color: C.muted, fontSize: 11, fontWeight: '800', width: 20, textAlign: 'center' }}>#{i + 1}</Text>
                <GradeChip grade={r.friction_grade} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }} numberOfLines={1}>{r.route}</Text>
                  <View style={{ flexDirection: 'row', gap: 12, marginTop: 4 }}>
                    <Text style={{ color: C.muted, fontSize: 10 }}>{r.visits} visits</Text>
                    {r.errors > 0 && <Text style={{ color: C.error, fontSize: 10 }}>{r.errors} errors</Text>}
                    {r.support_tickets > 0 && <Text style={{ color: C.warningText, fontSize: 10 }}>{r.support_tickets} tickets</Text>}
                    {r.negative_feedback > 0 && <Text style={{ color: C.error, fontSize: 10 }}>{r.negative_feedback} neg feedback</Text>}
                  </View>
                </View>
                <FrictionBar score={r.friction_score} />
                <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', minWidth: 30, textAlign: 'right' }}>{r.friction_score}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Full Heatmap */}
      <Text style={{ color: C.text, fontSize: 16, fontWeight: '800', marginBottom: 12 }}>{tx('admin.feedbackHeatmapPanel.auto.text.004', 'All Routes')}</Text>
      <View style={{ gap: 4 }}>
        {/* Header */}
        <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, gap: 8 }}>
          <Text style={{ flex: 1, color: C.muted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{tx('admin.feedbackHeatmapPanel.auto.text.005', 'Route')}</Text>
          <Text style={{ width: 50, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'right' }}>{tx('admin.feedbackHeatmapPanel.auto.text.006', 'Visits')}</Text>
          <Text style={{ width: 50, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'right' }}>{tx('admin.feedbackHeatmapPanel.auto.text.007', 'Errors')}</Text>
          <Text style={{ width: 50, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'right' }}>{tx('admin.feedbackHeatmapPanel.auto.text.008', 'LCP')}</Text>
          <Text style={{ width: 35, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.feedbackHeatmapPanel.auto.text.009', 'Grade')}</Text>
          <Text style={{ width: 80, color: C.muted, fontSize: 10, fontWeight: '700', textAlign: 'center' }}>{tx('admin.feedbackHeatmapPanel.auto.text.010', 'Friction')}</Text>
        </View>

        {heatmap.map((r: any, i: number) => (
          <View key={r.route} style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: i % 2 === 0 ? C.surface : 'transparent', gap: 8 }} data-testid={`heatmap-row-${i}`} testID={`heatmap-row-${i}`}>
            <Text style={{ flex: 1, color: C.text, fontSize: 11, fontWeight: '600' }} numberOfLines={1}>{r.route}</Text>
            <Text style={{ width: 50, color: C.text, fontSize: 11, fontWeight: '600', textAlign: 'right' }}>{r.visits}</Text>
            <Text style={{ width: 50, color: r.errors > 0 ? C.error : C.muted, fontSize: 11, fontWeight: '600', textAlign: 'right' }}>{r.errors}</Text>
            <Text style={{ width: 50, color: C.muted, fontSize: 11, textAlign: 'right' }}>{r.avg_lcp_ms > 0 ? `${r.avg_lcp_ms}ms` : '—'}</Text>
            <View style={{ width: 35, alignItems: 'center' }}><GradeChip grade={r.friction_grade} /></View>
            <FrictionBar score={r.friction_score} />
          </View>
        ))}
      </View>

      {heatmap.length === 0 && (
        <View style={{ padding: 40, alignItems: 'center' }}>
          <Ionicons name="analytics-outline" size={40} color={C.muted} />
          <Text style={{ color: C.muted, fontSize: 14, marginTop: 10 }}>{tx('admin.feedbackHeatmapPanel.auto.text.011', 'No route data available for this period')}</Text>
        </View>
      )}
    </View>
  );
}
