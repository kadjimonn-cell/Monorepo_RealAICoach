import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, Platform, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, Badge, StatCard } from './shared';
import { useTranslation } from '../../../hooks/useTranslation';

 
let LineChart: any, Line: any, XAxis: any, YAxis: any, CartesianGrid: any, Tooltip: any, Legend: any, ResponsiveContainer: any, Area: any, AreaChart: any;
if (Platform.OS === 'web') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const recharts = require('recharts');
  LineChart = recharts.LineChart;
  Line = recharts.Line;
  XAxis = recharts.XAxis;
  YAxis = recharts.YAxis;
  CartesianGrid = recharts.CartesianGrid;
  Tooltip = recharts.Tooltip;
  Legend = recharts.Legend;
  ResponsiveContainer = recharts.ResponsiveContainer;
  Area = recharts.Area;
  AreaChart = recharts.AreaChart;
}

interface Props {
  onResult: (result: { ok: boolean; msg: string }) => void;
}

export default function PerformanceChartsView({ onResult }: Props) {
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isWide = width >= 768;
  const [perfData, setPerfData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [expandedChart, setExpandedChart] = useState<string | null>(null);
  const [metricType, setMetricType] = useState<'open_rate' | 'click_rate'>('open_rate');
  const [simulating, setSimulating] = useState(false);

  const loadPerformance = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/ab-testing/performance');
      setPerfData(res.data);
    } catch { setPerfData(null); }
    finally { setLoading(false); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadPerformance(); }, []);

  const formatChartData = (timeSeries: any[]) => {
    const byDate: Record<string, any> = {};
    for (const entry of timeSeries) {
      const day = entry.date?.slice(5) || entry.date;
      if (!byDate[day]) byDate[day] = { date: day };
      const suffix = entry.variant === 'a' ? 'A' : 'B';
      byDate[day][`open_${suffix}`] = entry.open_rate;
      byDate[day][`click_${suffix}`] = entry.click_rate;
      byDate[day][`sent_${suffix}`] = entry.sent;
    }
    return Object.values(byDate).sort((a: any, b: any) => a.date.localeCompare(b.date));
  };

  if (Platform.OS !== 'web') {
    return (
      <View style={{ padding: 30, alignItems: 'center' }}>
        <Text style={{ color: C.muted }}>{tx('admin.emailTemplates.performanceCharts.states.webOnly', 'Charts are available on web only')}</Text>
      </View>
    );
  }

  return (
    <View style={{ marginTop: 24, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 20 }} data-testid="performance-charts-section" testID="performance-charts-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '20'), alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="trending-up" size={16} color={C.accent} />
          </View>
          <View>
            <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.emailTemplates.performanceCharts.header.title', 'Performance Trends')}</Text>
            <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.emailTemplates.performanceCharts.header.subtitle', 'A/B test open & click rate changes over time')}</Text>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          {/* Metric toggle */}
          <View style={{ flexDirection: 'row', backgroundColor: C.bg, borderRadius: 8, padding: 3 }} data-testid="metric-toggle" testID="metric-toggle">
            <TouchableOpacity
              onPress={() => setMetricType('open_rate')}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: metricType === 'open_rate' ? (globalThis as any).__alphaColor(C.green, '20') : 'transparent', borderWidth: 1, borderColor: metricType === 'open_rate' ? (globalThis as any).__alphaColor(C.green, '40') : 'transparent' }}
              data-testid="metric-open-rate" testID="metric-open-rate"
            >
              <Ionicons name="eye-outline" size={12} color={metricType === 'open_rate' ? C.green : C.muted} />
              <Text style={{ fontSize: 10, fontWeight: '600', color: metricType === 'open_rate' ? C.green : C.muted }}>{tx('admin.emailTemplates.performanceCharts.toggle.openRate', 'Open Rate')}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setMetricType('click_rate')}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 5, paddingHorizontal: 10, borderRadius: 6, backgroundColor: metricType === 'click_rate' ? (globalThis as any).__alphaColor(C.blue, '20') : 'transparent', borderWidth: 1, borderColor: metricType === 'click_rate' ? (globalThis as any).__alphaColor(C.blue, '40') : 'transparent' }}
              data-testid="metric-click-rate" testID="metric-click-rate"
            >
              <Ionicons name="hand-left-outline" size={12} color={metricType === 'click_rate' ? C.blue : C.muted} />
              <Text style={{ fontSize: 10, fontWeight: '600', color: metricType === 'click_rate' ? C.blue : C.muted }}>{tx('admin.emailTemplates.performanceCharts.toggle.clickRate', 'Click Rate')}</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity onPress={loadPerformance} style={{ padding: 8, borderRadius: 8, backgroundColor: C.bg }} data-testid="perf-refresh-btn" testID="perf-refresh-btn">
            <Ionicons name="refresh" size={14} color={C.muted} />
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={C.accent} style={{ marginVertical: 30 }} />
      ) : perfData && perfData.tests && perfData.tests.length > 0 ? (
        <View>
          {/* Platform-wide metrics */}
          {perfData.platform_metrics && (
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 20, flexWrap: 'wrap' }}>
              <StatCard val={perfData.platform_metrics.total_sends} label="Total A/B Sends" color={C.muted} />
              <StatCard val={`${perfData.platform_metrics.avg_open_rate}%`} label="Avg Open Rate" color={C.green} />
              <StatCard val={`${perfData.platform_metrics.avg_click_rate}%`} label="Avg Click Rate" color={C.blue} />
            </View>
          )}

          {/* Per-test charts */}
          {perfData.tests.map((test: any) => {
            const chartData = formatChartData(test.time_series || []);
            const isExpanded = expandedChart === test.test_id;
            const statusColor = test.status === 'active' ? C.green : test.status === 'completed' ? C.blue : C.muted;
            const hasData = chartData.length > 0;

            const lineKeyA = metricType === 'open_rate' ? 'open_A' : 'click_A';
            const lineKeyB = metricType === 'open_rate' ? 'open_B' : 'click_B';
            const colorA = C.blue;
            const colorB = C.purple;
            const metricLabel = metricType === 'open_rate' ? 'Open Rate' : 'Click Rate';

            return (
              <View key={test.test_id} style={{ backgroundColor: C.bg, borderRadius: 12, marginBottom: 12, borderWidth: 1, borderColor: isExpanded ? (globalThis as any).__alphaColor(C.accent, '40') : C.border, overflow: 'hidden' }} data-testid={`perf-chart-${test.test_id}`} testID={`perf-chart-${test.test_id}`}>
                {/* Header */}
                <TouchableOpacity
                  onPress={() => setExpandedChart(isExpanded ? null : test.test_id)}
                  style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14 }}
                  data-testid={`perf-chart-toggle-${test.test_id}`} testID={`perf-chart-toggle-${test.test_id}`}
                >
                  <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                    <View style={{ width: 32, height: 32, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '18'), alignItems: 'center', justifyContent: 'center' }}>
                      <Ionicons name="analytics" size={15} color={C.accent} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: '700', color: C.text }} numberOfLines={1}>
                        {test.name || test.template_type?.replace(/_/g, ' ') || 'Unnamed Test'}
                      </Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                        <Badge text={test.status} color={statusColor} />
                        {test.winner && <Badge text={`Winner: ${test.winner.toUpperCase()}`} color={C.green} />}
                        <Text style={{ fontSize: 10, color: C.muted }}>{chartData.length} data points</Text>
                      </View>
                    </View>
                  </View>
                  {/* Mini-comparison */}
                  <View style={{ flexDirection: 'row', gap: 12, marginRight: 8 }}>
                    <View style={{ alignItems: 'center' }}>
                      <Text style={{ fontSize: 14, fontWeight: '800', color: colorA }}>{test.totals?.a?.[metricType] || 0}%</Text>
                      <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.emailTemplates.performanceCharts.labels.variantA', 'Variant A')}</Text>
                    </View>
                    <View style={{ alignItems: 'center' }}>
                      <Text style={{ fontSize: 14, fontWeight: '800', color: colorB }}>{test.totals?.b?.[metricType] || 0}%</Text>
                      <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.emailTemplates.performanceCharts.labels.variantB', 'Variant B')}</Text>
                    </View>
                  </View>
                  <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={C.muted} />
                </TouchableOpacity>

                {/* Expanded Chart */}
                {isExpanded && (
                  <View style={{ padding: 14, borderTopWidth: 1, borderTopColor: C.border }}>
                    {/* Subject line comparison */}
                    <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 10, marginBottom: 16 }}>
                      <View style={{ flex: 1, padding: 10, backgroundColor: C.card, borderRadius: 8, borderLeftWidth: 3, borderLeftColor: colorA }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                          <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(colorA, '25'), alignItems: 'center', justifyContent: 'center' }}>
                            <Text style={{ fontSize: 8, fontWeight: '800', color: colorA }}>A</Text>
                          </View>
                          <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{tx('admin.emailTemplates.performanceCharts.labels.variantA', 'Variant A')}</Text>
                          {test.winner === 'a' && <Badge text="Winner" color={C.green} />}
                        </View>
                        <Text style={{ fontSize: 10, color: C.muted }} numberOfLines={2}>"{test.variant_a_subject || 'Original'}"</Text>
                        <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
                          <Text style={{ fontSize: 10, color: C.green }}>Open: {test.totals?.a?.open_rate || 0}%</Text>
                          <Text style={{ fontSize: 10, color: C.blue }}>Click: {test.totals?.a?.click_rate || 0}%</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>Sent: {test.totals?.a?.sent || 0}</Text>
                        </View>
                      </View>
                      <View style={{ flex: 1, padding: 10, backgroundColor: C.card, borderRadius: 8, borderLeftWidth: 3, borderLeftColor: colorB }}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                          <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(colorB, '25'), alignItems: 'center', justifyContent: 'center' }}>
                            <Text style={{ fontSize: 8, fontWeight: '800', color: colorB }}>B</Text>
                          </View>
                          <Text style={{ fontSize: 11, fontWeight: '700', color: C.text }}>{tx('admin.emailTemplates.performanceCharts.labels.variantB', 'Variant B')}</Text>
                          {test.winner === 'b' && <Badge text="Winner" color={C.green} />}
                        </View>
                        <Text style={{ fontSize: 10, color: C.muted }} numberOfLines={2}>"{test.variant_b_subject || 'AI Variant'}"</Text>
                        <View style={{ flexDirection: 'row', gap: 12, marginTop: 6 }}>
                          <Text style={{ fontSize: 10, color: C.green }}>Open: {test.totals?.b?.open_rate || 0}%</Text>
                          <Text style={{ fontSize: 10, color: C.blue }}>Click: {test.totals?.b?.click_rate || 0}%</Text>
                          <Text style={{ fontSize: 10, color: C.muted }}>Sent: {test.totals?.b?.sent || 0}</Text>
                        </View>
                      </View>
                    </View>

                    {/* Chart */}
                    {hasData ? (
                      <View style={{ backgroundColor: C.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: C.border }}>
                        <Text style={{ fontSize: 12, fontWeight: '700', color: C.text, marginBottom: 8 }}>{metricLabel} Over Time</Text>
                        <div style={{ width: '100%', height: 260 }}>
                          <ResponsiveContainer width="100%" height={260}>
                            <AreaChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                              <defs>
                                <linearGradient id={`grad_a_${test.test_id}`} x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor={colorA} stopOpacity={0.3}/>
                                  <stop offset="95%" stopColor={colorA} stopOpacity={0.02}/>
                                </linearGradient>
                                <linearGradient id={`grad_b_${test.test_id}`} x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="5%" stopColor={colorB} stopOpacity={0.3}/>
                                  <stop offset="95%" stopColor={colorB} stopOpacity={0.02}/>
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke={C.border} />
                              <XAxis dataKey="date" tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.border }} tickLine={false} />
                              <YAxis tick={{ fill: C.muted, fontSize: 10 }} axisLine={{ stroke: C.border }} tickLine={false} unit="%" domain={[0, 'auto']} />
                              <Tooltip
                                contentStyle={{ backgroundColor: C.card, border: `1px solid ${C.border}`, borderRadius: 8, fontSize: 11 }}
                                labelStyle={{ color: C.text, fontWeight: 700, marginBottom: 4 }}
                                itemStyle={{ color: C.muted }}
                                formatter={(value: any, name: string) => [`${value}%`, name.includes('A') ? 'Variant A' : 'Variant B']}
                              />
                              <Legend
                                wrapperStyle={{ fontSize: 10, color: C.muted }}
                                formatter={(value: string) => value.includes('A') ? 'Variant A' : 'Variant B'}
                              />
                              <Area type="monotone" dataKey={lineKeyA} stroke={colorA} strokeWidth={2} fill={`url(#grad_a_${test.test_id})`} dot={{ r: 3, fill: colorA }} activeDot={{ r: 5 }} />
                              <Area type="monotone" dataKey={lineKeyB} stroke={colorB} strokeWidth={2} fill={`url(#grad_b_${test.test_id})`} dot={{ r: 3, fill: colorB }} activeDot={{ r: 5 }} />
                            </AreaChart>
                          </ResponsiveContainer>
                        </div>
                      </View>
                    ) : (
                      <View style={{ padding: 24, alignItems: 'center', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
                        <Ionicons name="analytics-outline" size={28} color={C.border} />
                        <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.emailTemplates.performanceCharts.states.noTimeSeries', 'No time-series data yet. Data populates as emails are sent.')}</Text>
                      </View>
                    )}
                  </View>
                )}
              </View>
            );
          })}
        </View>
      ) : (
        <View style={{ alignItems: 'center', padding: 30, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
          <Ionicons name="trending-up-outline" size={36} color={C.border} />
          <Text style={{ fontSize: 13, color: C.muted, marginTop: 10 }}>{tx('admin.emailTemplates.performanceCharts.states.noPerformanceData', 'No performance data yet')}</Text>
          <Text style={{ fontSize: 11, color: C.muted, marginTop: 4, textAlign: 'center', maxWidth: 300 }}>
            {tx('admin.emailTemplates.performanceCharts.states.noPerformanceDataHelp', 'Create A/B tests and send tracked emails to see performance trends here. Charts will show open and click rate changes over time for each variant.')}
          </Text>
          <TouchableOpacity accessibilityLabel="Simulate perf button"
            onPress={async () => {
              setSimulating(true);
              try {
                await api.post('/ab-testing/performance/simulate');
                await loadPerformance();
                onResult({ ok: true, msg: 'Sample A/B performance data generated!' });
              } catch { onResult({ ok: false, msg: 'Failed to simulate data' }); }
              finally { setSimulating(false); }
            }}
            disabled={simulating}
            style={{ marginTop: 14, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 8, backgroundColor: simulating ? C.border : C.accent }}
            data-testid="simulate-perf-btn" testID="simulate-perf-btn"
          >
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.primaryText }}>{simulating ? 'Generating...' : 'Generate Sample Data'}</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}
