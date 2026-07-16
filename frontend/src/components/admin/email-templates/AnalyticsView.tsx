import { useTranslation } from '../../../hooks/useTranslation';
import React, { useState, useCallback, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, ScrollView, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../services/api';
import { C, RateBar } from './shared';
import { handleAppRecoverableError } from '../../../utils/appRecoverableError';

const tx = (_key: string, fallback: string) => fallback;

export default function AnalyticsView({ analytics }: { analytics: any }) {
  const onPrimary = 'rgb(255,255,255)';
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { width } = useWindowDimensions();
  const isWide = width >= 768;

  const [autofixRunning, setAutofixRunning] = useState(false);
  const [autofixHistory, setAutofixHistory] = useState<any[]>([]);
  const [overrides, setOverrides] = useState<any[]>([]);
  const [heatmapData, setHeatmapData] = useState<any>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);

  const loadAutofixData = useCallback(async () => {
    try {
      const [histRes, overRes] = await Promise.all([api.get('/email-notifications/autofix/history'), api.get('/email-notifications/autofix/overrides')]);
      setAutofixHistory(histRes.data || []); setOverrides(overRes.data || []);
    } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AnalyticsView.tsx#catch1', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, []);

  const triggerAutofix = useCallback(async () => {
    setAutofixRunning(true);
    try { await api.post('/email-notifications/autofix/run'); await loadAutofixData(); }
    catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AnalyticsView.tsx#catch2', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); } finally { setAutofixRunning(false); }
  }, [loadAutofixData]);

  const revertOverride = useCallback(async (emailType: string) => {
    try { await api.post(`/email-notifications/autofix/revert/${emailType}`); await loadAutofixData(); } catch (error) { handleAppRecoverableError({ scope: 'src/components/admin/email-templates/AnalyticsView.tsx#catch3', error, message: 'Something went wrong. Please retry.',
        notifyMode: 'silent',
      }); }
  }, [loadAutofixData]);

  const loadHeatmap = useCallback(async () => {
    setHeatmapLoading(true);
    try {
      const res = await api.get('/email-notifications/analytics/click-heatmap');
      setHeatmapData(res.data);
    } catch { setHeatmapData(null); }
    finally { setHeatmapLoading(false); }
  }, []);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAutofixData(); loadHeatmap(); }, []);

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border }} data-testid="analytics-section" testID="analytics-section">
      <Text style={{ fontSize: 16, fontWeight: '800', color: C.text, marginBottom: 4 }}>{tx('admin.analyticsView.auto.text.001', 'Email Performance Analytics')}</Text>
      <Text style={{ fontSize: 12, color: C.muted, marginBottom: 16 }}>{tx('admin.analyticsView.auto.text.002', 'Open and click tracking across all email types. Data updates as recipients interact.')}</Text>

      {analytics?.totals?.sent > 0 ? (
        <View>
          {/* Summary KPIs */}
          <View style={{ flexDirection: 'row', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'Total Tracked', val: analytics.totals.sent, color: C.muted },
              { label: 'Unique Opens', val: analytics.totals.opened, color: C.green },
              { label: 'Unique Clicks', val: analytics.totals.clicked, color: C.blue },
              { label: 'Total Opens', val: analytics.totals.total_opens, color: C.accent },
              { label: 'Total Clicks', val: analytics.totals.total_clicks, color: C.purpleText },
            ].map(s => (
              <View key={s.label} style={{ padding: 12, backgroundColor: (globalThis as any).__alphaColor(s.color, '0A'), borderRadius: 10, minWidth: 90, flex: 1, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(s.color, '18') }}>
                <Text style={{ fontSize: 18, fontWeight: '800', color: s.color }}>{s.val}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{s.label}</Text>
              </View>
            ))}
          </View>

          {/* Open/Click Rate Visual Summary */}
          <View style={{ flexDirection: isWide ? 'row' : 'column', gap: 12, marginBottom: 20 }}>
            <View style={{ flex: 1, padding: 16, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Ionicons name="eye-outline" size={14} color={C.green} />
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.analyticsView.auto.text.003', 'Open Rate')}</Text>
              </View>
              <Text style={{ fontSize: 32, fontWeight: '800', color: C.green, marginBottom: 4 }}>{analytics.totals.open_rate}%</Text>
              <RateBar rate={analytics.totals.open_rate} color={C.green} />
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{analytics.totals.opened} of {analytics.totals.sent} emails opened</Text>
            </View>
            <View style={{ flex: 1, padding: 16, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Ionicons name="hand-left-outline" size={14} color={C.blue} />
                <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }}>{tx('admin.analyticsView.auto.text.004', 'Click Rate')}</Text>
              </View>
              <Text style={{ fontSize: 32, fontWeight: '800', color: C.blue, marginBottom: 4 }}>{analytics.totals.click_rate}%</Text>
              <RateBar rate={analytics.totals.click_rate} color={C.blue} />
              <Text style={{ fontSize: 10, color: C.muted, marginTop: 6 }}>{analytics.totals.clicked} of {analytics.totals.sent} emails clicked</Text>
            </View>
          </View>

          {/* Per-Template Performance Table */}
          <View data-testid="analytics-per-type-table" testID="analytics-per-type-table">
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.analyticsView.auto.text.005', 'Performance by Template')}</Text>
            <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.bg, borderRadius: 8 }}>
              <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: C.muted }}>{tx('admin.analyticsView.auto.text.006', 'TEMPLATE')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.007', 'SENT')}</Text>
              <Text style={{ flex: 1.5, fontSize: 10, fontWeight: '700', color: C.muted, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.008', 'OPEN RATE')}</Text>
              <Text style={{ flex: 1.5, fontSize: 10, fontWeight: '700', color: C.muted, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.009', 'CLICK RATE')}</Text>
            </View>
            {Object.entries(analytics.by_type).sort(([, a]: any, [, b]: any) => b.sent - a.sent).map(([type, data]: [string, any]) => (
              <View key={type} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30') }}>
                <View style={{ flex: 2 }}>
                  <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }} numberOfLines={1}>{type.replace(/_/g, ' ')}</Text>
                  <Text style={{ fontSize: 9, color: C.muted }}>{data.opened} opens / {data.clicked} clicks</Text>
                </View>
                <Text style={{ flex: 1, fontSize: 12, color: C.muted, textAlign: 'center', fontWeight: '600' }}>{data.sent}</Text>
                <View style={{ flex: 1.5, paddingHorizontal: 4 }}>
                  <RateBar rate={data.open_rate} color={data.open_rate > 30 ? C.green : data.open_rate > 15 ? C.blue : C.red} />
                </View>
                <View style={{ flex: 1.5, paddingHorizontal: 4 }}>
                  <RateBar rate={data.click_rate} color={data.click_rate > 5 ? C.green : data.click_rate > 2 ? C.blue : C.muted} />
                </View>
              </View>
            ))}
          </View>
        </View>
      ) : (
        <View style={{ alignItems: 'center', padding: 40 }}>
          <Ionicons name="analytics-outline" size={48} color={C.border} />
          <Text style={{ fontSize: 14, color: C.muted, marginTop: 12 }}>{tx('admin.analyticsView.auto.text.010', 'No analytics data yet')}</Text>
          <Text style={{ fontSize: 12, color: C.muted, marginTop: 4, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.011', 'Data will appear as emails are sent and recipients interact.')}</Text>
        </View>
      )}

      {/* Click-Through Heatmap */}
      <View style={{ marginTop: 24, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 20 }} data-testid="click-heatmap-section" testID="click-heatmap-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.error, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="flame" size={14} color={C.error} />
            </View>
            <View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.analyticsView.auto.text.012', 'Click-Through Heatmap')}</Text>
              <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.analyticsView.auto.text.013', 'Which CTA buttons get the most engagement across templates')}</Text>
            </View>
          </View>
          <TouchableOpacity onPress={loadHeatmap} style={{ padding: 8, borderRadius: 8, backgroundColor: C.bg }} data-testid="heatmap-refresh-btn" testID="heatmap-refresh-btn">
            <Ionicons name="refresh" size={16} color={C.muted} />
          </TouchableOpacity>
        </View>

        {heatmapLoading ? (
          <ActivityIndicator size="large" color={C.error} style={{ marginVertical: 30 }} />
        ) : heatmapData && heatmapData.total_click_events > 0 ? (
          <View>
            {/* Summary KPIs */}
            <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
              <View style={{ flex: 1, minWidth: 80, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.error, '0A'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.error, '18'), alignItems: 'center' }}>
                <Text style={{ fontSize: 20, fontWeight: '800', color: C.error }}>{heatmapData.total_click_events}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.analyticsView.auto.text.014', 'Total Clicks')}</Text>
              </View>
              <View style={{ flex: 1, minWidth: 80, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.purple, '0A'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.purple, '18'), alignItems: 'center' }}>
                <Text style={{ fontSize: 20, fontWeight: '800', color: C.purpleText }}>{heatmapData.top_urls?.length || 0}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.analyticsView.auto.text.015', 'Unique URLs')}</Text>
              </View>
              <View style={{ flex: 1, minWidth: 80, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.blue, '0A'), borderRadius: 10, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.blue, '18'), alignItems: 'center' }}>
                <Text style={{ fontSize: 20, fontWeight: '800', color: C.blue }}>{heatmapData.top_templates?.length || 0}</Text>
                <Text style={{ fontSize: 10, color: C.muted }}>{tx('admin.analyticsView.auto.text.016', 'Active Templates')}</Text>
              </View>
            </View>

            {/* Top CTAs by Clicks */}
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.analyticsView.auto.text.017', 'Top CTA Destinations')}</Text>
            {(heatmapData.top_urls || []).slice(0, 10).map((u: any, idx: number) => {
              const intensity = heatmapData.max_clicks ? u.total_clicks / heatmapData.max_clicks : 0;
              const barColor = intensity > 0.7 ? C.error : intensity > 0.4 ? C.warning : intensity > 0.15 ? C.blue : C.muted;
              return (
                <View key={idx} style={{ marginBottom: 8, padding: 12, backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border, borderLeftWidth: 3, borderLeftColor: barColor }} data-testid={`heatmap-url-${idx}`} testID={`heatmap-url-${idx}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                    <View style={{ flex: 1, marginRight: 12 }}>
                      <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }} numberOfLines={1}>{u.label}</Text>
                      <Text style={{ fontSize: 9, color: C.muted, marginTop: 2 }} numberOfLines={1}>{(u.templates || []).map((t: any) => t.template?.replace(/_/g, ' ')).join(', ')}</Text>
                    </View>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={{ fontSize: 16, fontWeight: '800', color: barColor }}>{u.total_clicks}</Text>
                      <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.analyticsView.auto.text.018', 'clicks')}</Text>
                    </View>
                  </View>
                  <View style={{ height: 4, backgroundColor: C.border, borderRadius: 2, overflow: 'hidden' }}>
                    <View style={{ width: `${Math.max(intensity * 100, 2)}%`, height: '100%', backgroundColor: barColor, borderRadius: 2 }} />
                  </View>
                </View>
              );
            })}

            {/* Template engagement ranking */}
            <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10, marginTop: 20 }}>{tx('admin.analyticsView.auto.text.019', 'Template Click Engagement')}</Text>
            <View style={{ flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: C.border, backgroundColor: C.bg, borderRadius: 8 }}>
              <Text style={{ flex: 0.3, fontSize: 10, fontWeight: '700', color: C.muted }}>#</Text>
              <Text style={{ flex: 2, fontSize: 10, fontWeight: '700', color: C.muted }}>{tx('admin.analyticsView.auto.text.020', 'TEMPLATE')}</Text>
              <Text style={{ flex: 1, fontSize: 10, fontWeight: '700', color: C.muted, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.021', 'CLICKS')}</Text>
              <Text style={{ flex: 1.5, fontSize: 10, fontWeight: '700', color: C.muted, textAlign: 'center' }}>{tx('admin.analyticsView.auto.text.022', 'HEAT')}</Text>
            </View>
            {(heatmapData.top_templates || []).map((t: any, idx: number) => {
              const maxT = heatmapData.top_templates?.[0]?.total_clicks || 1;
              const pct = Math.round((t.total_clicks / maxT) * 100);
              const heatColor = pct > 70 ? C.error : pct > 40 ? C.warning : pct > 15 ? C.blue : C.muted;
              return (
                <View key={t.template} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: (globalThis as any).__alphaColor(C.border, '30') }} data-testid={`heatmap-template-${idx}`} testID={`heatmap-template-${idx}`}>
                  <Text style={{ flex: 0.3, fontSize: 11, fontWeight: '700', color: C.muted }}>{idx + 1}</Text>
                  <View style={{ flex: 2 }}>
                    <Text style={{ fontSize: 12, fontWeight: '600', color: C.text }} numberOfLines={1}>{t.template?.replace(/_/g, ' ')}</Text>
                    <Text style={{ fontSize: 9, color: C.muted }}>{(t.urls || []).length} unique URLs</Text>
                  </View>
                  <Text style={{ flex: 1, fontSize: 13, color: heatColor, textAlign: 'center', fontWeight: '700' }}>{t.total_clicks}</Text>
                  <View style={{ flex: 1.5, paddingHorizontal: 4 }}>
                    <View style={{ height: 6, backgroundColor: C.border, borderRadius: 3, overflow: 'hidden' }}>
                      <View style={{ width: `${pct}%`, height: '100%', borderRadius: 3, backgroundColor: heatColor }} />
                    </View>
                  </View>
                </View>
              );
            })}

            {/* Heatmap Grid */}
            {heatmapData.heatmap && heatmapData.heatmap.length > 0 && (
              <View style={{ marginTop: 20 }}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: C.text, marginBottom: 10 }}>{tx('admin.analyticsView.auto.text.023', 'Click Distribution Grid')}</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                  <View>
                    {(() => {
                      const templates = Array.from(new Set(heatmapData.heatmap.map((c: any) => c.template))).slice(0, 12) as string[];
                      const labels = Array.from(new Set(heatmapData.heatmap.map((c: any) => c.label))).slice(0, 8) as string[];
                      const clickMap: Record<string, number> = {};
                      heatmapData.heatmap.forEach((c: any) => { clickMap[`${c.template}::${c.label}`] = c.clicks; });
                      return (
                        <View>
                          <View style={{ flexDirection: 'row' }}>
                            <View style={{ width: 110, padding: 6 }} />
                            {labels.map((l: string) => (
                              <View key={l} style={{ width: 72, padding: 4, alignItems: 'center' }}>
                                <Text style={{ fontSize: 8, color: C.muted, fontWeight: '600', textAlign: 'center' }} numberOfLines={2}>{l}</Text>
                              </View>
                            ))}
                          </View>
                          {templates.map((tpl: string) => (
                            <View key={tpl} style={{ flexDirection: 'row', alignItems: 'center' }}>
                              <View style={{ width: 110, padding: 6 }}>
                                <Text style={{ fontSize: 9, color: C.text, fontWeight: '600' }} numberOfLines={1}>{tpl.replace(/_/g, ' ')}</Text>
                              </View>
                              {labels.map((l: string) => {
                                const val = clickMap[`${tpl}::${l}`] || 0;
                                const norm = heatmapData.max_clicks ? val / heatmapData.max_clicks : 0;
                                const cellBg = val === 0 ? C.border + '30' : norm > 0.7 ? C.error : norm > 0.4 ? C.warning : norm > 0.15 ? C.blue : C.accent;
                                const opacity = val === 0 ? 0.3 : 0.15 + norm * 0.85;
                                return (
                                  <View key={l} style={{ width: 72, height: 32, margin: 2, borderRadius: 6, backgroundColor: cellBg, opacity, alignItems: 'center', justifyContent: 'center' }} data-testid={`heatmap-cell-${tpl}-${l}`} testID={`heatmap-cell-${tpl}-${l}`}>
                                    <Text style={{ fontSize: 10, fontWeight: '700', color: onPrimary }}>{val || ''}</Text>
                                  </View>
                                );
                              })}
                            </View>
                          ))}
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 10, paddingLeft: 110 }}>
                            <Text style={{ fontSize: 9, color: C.muted }}>{tx('admin.analyticsView.auto.text.024', 'Intensity:')}</Text>
                            {[{ label: 'Low', color: C.accent }, { label: 'Medium', color: C.blue }, { label: 'High', color: C.warningText }, { label: 'Hot', color: C.error }].map(l => (
                              <View key={l.label} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                                <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: l.color }} />
                                <Text style={{ fontSize: 8, color: C.muted }}>{l.label}</Text>
                              </View>
                            ))}
                          </View>
                        </View>
                      );
                    })()}
                  </View>
                </ScrollView>
              </View>
            )}
          </View>
        ) : (
          <View style={{ alignItems: 'center', padding: 30, backgroundColor: C.bg, borderRadius: 12, borderWidth: 1, borderColor: C.border }}>
            <Ionicons name="flame-outline" size={36} color={C.border} />
            <Text style={{ fontSize: 13, color: C.muted, marginTop: 10 }}>{tx('admin.analyticsView.auto.text.025', 'No click data yet')}</Text>
            <Text style={{ fontSize: 11, color: C.muted, marginTop: 4, textAlign: 'center', maxWidth: 300 }}>{tx('admin.analyticsView.auto.text.026', 'Click-through heatmaps will populate as recipients interact with your emails. Send tracked emails to start collecting data.')}</Text>
          </View>
        )}
      </View>

      {/* Safe Auto-Fix */}
      <View style={{ marginTop: 24, borderTopWidth: 1, borderTopColor: C.border, paddingTop: 20 }} data-testid="autofix-section" testID="autofix-section">
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(C.accent, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="construct" size={14} color={C.accent} />
            </View>
            <View>
              <Text style={{ fontSize: 15, fontWeight: '800', color: C.text }}>{tx('admin.analyticsView.auto.text.027', 'Safe Auto-Fix')}</Text>
              <Text style={{ fontSize: 11, color: C.muted }}>{tx('admin.analyticsView.auto.text.028', 'AI detects underperforming emails and optimizes subject lines')}</Text>
            </View>
          </View>
          <TouchableOpacity onPress={triggerAutofix} disabled={autofixRunning} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: autofixRunning ? C.border : C.accent, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 }} data-testid="autofix-run-btn" testID="autofix-run-btn">
            {autofixRunning ? <ActivityIndicator size="small" color={onPrimary} /> : <Ionicons name="flash" size={14} color={onPrimary} />}
            <Text style={{ color: onPrimary, fontWeight: '700', fontSize: 12 }}>{autofixRunning ? 'Analyzing...' : 'Run Analysis'}</Text>
          </TouchableOpacity>
        </View>
        {overrides.length > 0 && (
          <View style={{ marginBottom: 16 }} data-testid="autofix-overrides" testID="autofix-overrides">
            <Text style={{ fontSize: 12, fontWeight: '700', color: C.green, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>Active Overrides ({overrides.length})</Text>
            {overrides.map((ov: any) => (
              <View key={ov.email_type} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: (globalThis as any).__alphaColor(C.green, '08'), borderRadius: 10, marginBottom: 6, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.green, '20') }} data-testid={`override-${ov.email_type}`} testID={`override-${ov.email_type}`}>
                <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: C.green }} />
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={{ fontSize: 12, fontWeight: '700', color: C.text }} numberOfLines={1}>{ov.email_type?.replace(/_/g, ' ')}</Text>
                  <Text style={{ fontSize: 10, color: C.muted, marginTop: 2 }} numberOfLines={1}>Original: {ov.original_subject}</Text>
                  <Text style={{ fontSize: 10, color: C.green, marginTop: 1 }} numberOfLines={1}>Optimized: {ov.optimized_subject}</Text>
                </View>
                <TouchableOpacity onPress={() => revertOverride(ov.email_type)} style={{ paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, backgroundColor: (globalThis as any).__alphaColor(C.red, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(C.red, '30') }} data-testid={`revert-${ov.email_type}`} testID={`revert-${ov.email_type}`}>
                  <Text style={{ fontSize: 10, fontWeight: '700', color: C.red }}>{tx('admin.analyticsView.auto.text.029', 'Revert')}</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}
        <View data-testid="autofix-history" testID="autofix-history">
          <Text style={{ fontSize: 12, fontWeight: '700', color: C.muted, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>{tx('admin.analyticsView.auto.text.030', 'Run History')}</Text>
          {autofixHistory.length === 0 ? (
            <View style={{ padding: 24, alignItems: 'center', backgroundColor: C.bg, borderRadius: 10, borderWidth: 1, borderColor: C.border }}>
              <Ionicons name="time-outline" size={28} color={C.border} />
              <Text style={{ fontSize: 12, color: C.muted, marginTop: 8 }}>{tx('admin.analyticsView.auto.text.031', 'No runs yet. Click "Run Analysis" to start.')}</Text>
            </View>
          ) : autofixHistory.slice(0, 8).map((run: any, idx: number) => {
            const sc = run.status === 'healthy' ? C.green : run.status === 'fixed' ? C.blue : C.muted;
            return (
              <View key={idx} style={{ padding: 12, backgroundColor: C.bg, borderRadius: 10, marginBottom: 6, borderWidth: 1, borderColor: C.border }} data-testid={`history-run-${idx}`} testID={`history-run-${idx}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name={run.status === 'healthy' ? 'checkmark-circle' : 'build'} size={14} color={sc} />
                    <Text style={{ fontSize: 12, fontWeight: '700', color: sc, textTransform: 'capitalize' }}>{run.status}</Text>
                  </View>
                  <Text style={{ fontSize: 10, color: C.muted }}>{run.run_at ? new Date(run.run_at).toLocaleString() : ''}</Text>
                </View>
                <View style={{ flexDirection: 'row', gap: 12 }}>
                  <Text style={{ fontSize: 11, color: C.muted }}><Text style={{ fontWeight: '700' }}>{run.underperformers || 0}</Text> underperforming</Text>
                  <Text style={{ fontSize: 11, color: C.blue }}><Text style={{ fontWeight: '700' }}>{run.fixes_applied || 0}</Text> fixed</Text>
                </View>
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}
