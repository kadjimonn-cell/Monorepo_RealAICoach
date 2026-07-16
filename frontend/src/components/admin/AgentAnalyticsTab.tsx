import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

type Props = { C: any; isCompact: boolean };

const SEVERITY_ICON: Record<string, string> = { high: 'alert-circle', medium: 'warning', low: 'information-circle' };

export const AgentAnalyticsTab: React.FC<Props> = ({ C, isCompact }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [overview, setOverview] = useState<any>(null);
  const [trends, setTrends] = useState<any>(null);
  const [recs, setRecs] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [adoption, setAdoption] = useState<any[]>([]);
  const [showAllRecs, setShowAllRecs] = useState(false);

  const load = useCallback(async () => {
    try {
      setError(null);
      const [ov, tr, rc, al, ad] = await Promise.all([
        api.get('/agent-framework/analytics/overview'),
        api.get('/agent-framework/analytics/trends?days=30'),
        api.get('/agent-framework/analytics/recommendations'),
        api.get('/agent-framework/analytics/alerts'),
        api.get('/agent-framework/analytics/adoption'),
      ]);
      setOverview(ov.data);
      setTrends(tr.data);
      setRecs(rc.data?.recommendations || []);
      setAlerts(al.data?.alerts || []);
      setAdoption(ad.data?.features || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const s = makeStyles(C, isCompact);

  if (loading) {
    return <View style={s.center} testID="analytics-loading"><ActivityIndicator size="large" color={C.primary} /></View>;
  }
  if (error) {
    return <View style={s.errorBox}><Text style={{ color: C.errorText }} testID="analytics-error">{error}</Text></View>;
  }

  const series = trends?.series || [];
  const maxExec = Math.max(1, ...series.map((d: any) => d.executions));
  const visibleRecs = showAllRecs ? recs : recs.slice(0, 8);

  return (
    <View testID="agent-analytics-tab">
      {/* KPI cards */}
      <View style={s.statsRow} testID="analytics-stats">
        {[
          { label: 'Executions', value: overview?.executions_total, icon: 'play-circle' },
          { label: 'Success Rate', value: `${overview?.success_rate_percent ?? 0}%`, icon: 'checkmark-circle' },
          { label: 'Avg Latency', value: `${overview?.avg_latency_ms ?? 0}ms`, icon: 'speedometer' },
          { label: 'Est. Cost', value: `$${overview?.est_cost_usd_total ?? 0}`, icon: 'cash' },
          { label: 'Est. Tokens', value: overview?.est_tokens_total, icon: 'layers' },
          { label: 'Satisfaction', value: overview?.avg_satisfaction ?? '—', icon: 'happy' },
        ].map((card) => (
          <View key={card.label} style={s.statCard} testID={`analytics-stat-${card.label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`}>
            <Ionicons name={card.icon as any} size={16} color={C.primary} />
            <Text style={s.statValue}>{card.value ?? '—'}</Text>
            <Text style={s.statLabel}>{card.label}</Text>
          </View>
        ))}
      </View>

      {/* Alerts */}
      <View style={s.panel} testID="analytics-alerts-panel">
        <View style={s.panelHeader}>
          <Text style={s.panelTitle}>Health Alerts</Text>
          <View style={[s.badge, { backgroundColor: alerts.length ? C.errorSoft : C.successSoft }]}>
            <Text style={[s.badgeText, { color: alerts.length ? C.errorText : C.successText }]} testID="analytics-alerts-count">
              {alerts.length ? `${alerts.length} ACTIVE` : 'ALL CLEAR'}
            </Text>
          </View>
        </View>
        {alerts.length === 0 ? <Text style={s.meta}>No degraded agents or sync failures detected.</Text> : alerts.map((a) => (
          <View key={a.alert_id} style={s.lineRow} testID={`analytics-alert-${a.alert_id}`}>
            <Ionicons name="alert-circle" size={14} color={C.errorText} />
            <Text style={s.lineLabel} numberOfLines={2}>{a.message}</Text>
          </View>
        ))}
      </View>

      {/* 30-day trend */}
      <View style={s.panel} testID="analytics-trends-panel">
        <Text style={s.panelTitle}>30-Day Execution Trend</Text>
        {series.length === 0 ? <Text style={s.meta}>No execution data recorded yet — daily time-series will appear after agents run.</Text> : (
          <View>
            <View style={s.chartRow}>
              {series.slice(-30).map((d: any) => (
                <View key={d.date} style={s.barCol}>
                  <View style={[s.bar, { height: Math.max(3, (d.executions / maxExec) * 60), backgroundColor: d.errors > 0 ? C.warningText : C.primary }]} />
                </View>
              ))}
            </View>
            <View style={s.trendMetaRow}>
              <Text style={s.meta}>{series[0]?.date} → {series[series.length - 1]?.date}</Text>
              <Text style={s.meta}>
                {series.reduce((t: number, d: any) => t + d.executions, 0)} runs · ${series.reduce((t: number, d: any) => t + (d.est_cost_usd || 0), 0).toFixed(4)} est.
              </Text>
            </View>
          </View>
        )}
      </View>

      {/* Optimization recommendations */}
      <View style={s.panel} testID="analytics-recommendations-panel">
        <View style={s.panelHeader}>
          <Text style={s.panelTitle}>Optimization Recommendations</Text>
          <Text style={s.meta} testID="analytics-recs-count">{recs.length} total</Text>
        </View>
        {recs.length === 0 ? <Text style={s.meta}>No optimizations needed — fleet is healthy.</Text> : visibleRecs.map((r, i) => (
          <View key={`${r.agent_key}-${r.type}-${i}`} style={s.recRow} testID={`analytics-rec-${r.agent_key}-${r.type}`}>
            <Ionicons
              name={SEVERITY_ICON[r.severity] as any}
              size={15}
              color={r.severity === 'high' ? C.errorText : r.severity === 'medium' ? C.warningText : C.textDim}
            />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.lineLabel} numberOfLines={1}>{r.name}</Text>
              <Text style={s.meta} numberOfLines={2}>{r.recommendation}</Text>
            </View>
          </View>
        ))}
        {recs.length > 8 ? (
          <TouchableOpacity onPress={() => setShowAllRecs(!showAllRecs)} style={s.moreBtn} testID="analytics-recs-toggle" accessibilityLabel="Interactive element">
            <Text style={s.moreBtnText}>{showAllRecs ? 'Show fewer' : `Show all ${recs.length}`}</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Feature adoption + top agents */}
      <View style={s.rowWrap}>
        <View style={s.panel} testID="analytics-adoption-panel">
          <Text style={s.panelTitle}>Feature Adoption</Text>
          {adoption.length === 0 ? <Text style={s.meta}>No routing or specialist-strip activity yet.</Text> : adoption.slice(0, 10).map((f) => (
            <View key={f.feature_key} style={s.lineRow}>
              <Ionicons name="apps" size={13} color={C.primary} />
              <Text style={s.lineLabel} numberOfLines={1}>{f.feature_key}</Text>
              <Text style={s.lineValue}>{f.routes} routes · {f.strip_clicks} clicks</Text>
            </View>
          ))}
        </View>
        <View style={s.panel} testID="analytics-top-agents-panel">
          <Text style={s.panelTitle}>Top Agents by Utilization</Text>
          {(overview?.top_agents || []).length === 0 ? <Text style={s.meta}>No executions recorded yet.</Text> : overview.top_agents.map((a: any) => (
            <View key={a.agent_key} style={s.lineRow}>
              <Ionicons name="person-circle" size={13} color={C.primary} />
              <Text style={s.lineLabel} numberOfLines={1}>{a.agent_key}</Text>
              <Text style={s.lineValue}>{a.executions}</Text>
            </View>
          ))}
        </View>
      </View>
    </View>
  );
};

const makeStyles = (C: any, isCompact: boolean) => StyleSheet.create({
  center: { padding: 40, alignItems: 'center' },
  errorBox: { backgroundColor: C.errorSoft, borderRadius: 10, padding: 12, marginBottom: 12 },
  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  statCard: {
    flexGrow: 1, minWidth: isCompact ? 100 : 130, backgroundColor: C.card, borderRadius: 12,
    borderWidth: 1, borderColor: C.border, padding: 12, gap: 4,
  },
  statValue: { fontSize: 18, fontWeight: '800', color: C.text },
  statLabel: { fontSize: 11, color: C.textSecondary },
  panel: {
    flex: 1, backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.border,
    padding: 16, marginBottom: 12,
  },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  panelTitle: { fontSize: 14, fontWeight: '700', color: C.text, marginBottom: 6 },
  badge: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: '800' },
  lineRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  lineLabel: { fontSize: 12, color: C.textSecondary, flexShrink: 1 },
  lineValue: { fontSize: 11, fontWeight: '700', color: C.text, marginLeft: 'auto' },
  meta: { fontSize: 11, color: C.textDim, marginTop: 2, lineHeight: 16 },
  chartRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 3, height: 64, marginTop: 6 },
  barCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  bar: { width: '80%', maxWidth: 14, borderRadius: 3 },
  trendMetaRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8, flexWrap: 'wrap', gap: 4 },
  recRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 7,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.border,
  },
  rowWrap: { flexDirection: isCompact ? 'column' : 'row', gap: 12 },
  moreBtn: { marginTop: 10, alignSelf: 'flex-start', paddingVertical: 6, paddingHorizontal: 14, borderRadius: 999, backgroundColor: C.primarySoft },
  moreBtnText: { fontSize: 12, fontWeight: '700', color: C.accentText },
});

export default AgentAnalyticsTab;
