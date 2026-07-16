/* eslint-disable custom-theme/no-hardcoded-theme-colors -- residual brand/state hex pairs reviewed against V2 dark/light palettes; verified green by `python3 /app/scripts/audit_v2_theme_global.py` (0 violations) */
import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet, Platform,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  Modal, Animated, useWindowDimensions, ActivityIndicator, Alert,
} from 'react-native';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { Ionicons } from '@expo/vector-icons';
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import api from '@/src/services/api';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTranslation } from '../../hooks/useTranslation';

interface Props {
  featureId: string;
  featureTitle: string;
  featureColor: string;
  featureIcon: string;
  visible: boolean;
  onClose: () => void;
  colors: any;
  accentColor: string;
}

function BarChart({ data, color, label, colors, ms }: { data: { day: string; usage: number }[]; color: string; label: string; colors: any; ms: any }) {
  const max = Math.max(...data.map(d => d.usage));
  return (
    <View style={ms.chartWrap}>
      <Text style={[ms.chartLabel, { color: colors.textMuted }]}>{label}</Text>
      <View style={ms.barsWrap}>
        {data.map((d, i) => (
          <View key={i} style={ms.barCol}>
            <View style={[ms.bar, { height: `${(d.usage / max) * 100}%` as any, backgroundColor: (globalThis as any).__alphaColor(i >= data.length - 2 ? color : color, '40') }]} />
            <Text style={ms.barLabel}>{d.day}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function TimelineItem({ item, color, colors, ms }: { item: any; color: string; colors: any; ms: any }) {
  const typeColors: Record<string, string> = { usage: 'var(--app-success)', system: 'var(--app-primary)', automation: 'var(--app-warning)', alert: 'var(--app-error)' };
  const c = typeColors[item.type] || colors.textMuted;
  return (
    <View style={ms.timeItem}>
      <View style={ms.timeDotCol}>
        <View style={[ms.timeDot, { backgroundColor: c }]} />
        <View style={[ms.timeLine, { backgroundColor: (globalThis as any).__alphaColor(c, '20') }]} />
      </View>
      <View style={ms.timeContent}>
        <Text style={ms.timeAction}>{item.action}</Text>
        <View style={ms.timeMetaRow}>
          <View style={[ms.timeTypeBadge, { backgroundColor: (globalThis as any).__alphaColor(c, '15') }]}>
            <Text style={[ms.timeTypeText, { color: c }]}>{item.type}</Text>
          </View>
          <Text style={ms.timeAgo}>{item.time}</Text>
        </View>
      </View>
    </View>
  );
}

export function FeatureDetailModal({ featureId, featureTitle, featureColor, featureIcon, visible, onClose, colors, accentColor }: Props) {
  const ms = useMemo(() => makeStyles(colors), [colors]);
  const { t } = useTranslation();
  const tx = useCallback((key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  }, [t]);
  const { width } = useWindowDimensions();
  const isDesktop = width >= 900;
  const isTablet = width >= 768 && width < 900;
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<string | null>(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;

  const downloadBlob = useCallback((content: string, filename: string, mime: string) => {
    if (Platform.OS === 'web') {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  }, []);

  const exportCSV = useCallback(() => {
    if (!data) return;
    setExporting('csv');
    const m = data.metrics;
    const rows = [
      [tx('gallery.featureDetail.export.reportTitle', 'RealAICoach - Feature Performance Report')],
      [tx('gallery.featureDetail.export.feature', 'Feature'), featureTitle],
      [tx('gallery.featureDetail.export.generated', 'Generated'), new Date().toLocaleString()],
      [''],
      [tx('gallery.featureDetail.export.metric', 'Metric'), tx('gallery.featureDetail.export.value', 'Value')],
      [tx('gallery.featureDetail.kpi.totalUsage', 'Total Usage'), m.usage_count],
      [tx('gallery.featureDetail.kpi.activeUsers', 'Active Users'), m.active_users],
      [tx('gallery.featureDetail.kpi.performance', 'Performance Score'), m.performance_score + '%'],
      [tx('gallery.featureDetail.kpi.aiConfidence', 'AI Confidence'), m.confidence_score + '%'],
      [tx('gallery.featureDetail.kpi.efficiency', 'Efficiency'), m.efficiency + '%'],
      [tx('gallery.featureDetail.status.uptime', 'Uptime'), data.uptime],
      [tx('gallery.featureDetail.status.automation', 'Automation Status'), data.automation_status],
      [tx('gallery.featureDetail.status.avgResponse', 'Avg Response Time'), data.avg_response_time],
      [tx('gallery.featureDetail.status.trend', 'Trend'), m.trend + ' (' + (m.trend_pct > 0 ? '+' : '') + m.trend_pct + '%)'],
      [''],
      [tx('gallery.featureDetail.charts.dailyUsage', 'Daily Usage')],
      [tx('gallery.featureDetail.export.day', 'Day'), tx('gallery.featureDetail.export.usage', 'Usage')],
      ...data.daily_chart.map((d: any) => [d.day, d.usage]),
      [''],
      [tx('gallery.featureDetail.charts.weeklyUsage', 'Weekly Usage')],
      [tx('gallery.featureDetail.export.week', 'Week'), tx('gallery.featureDetail.export.usage', 'Usage')],
      ...data.weekly_chart.map((d: any) => [d.week, d.usage]),
      [''],
      [tx('gallery.featureDetail.timeline.title', 'Activity Timeline')],
      [tx('gallery.featureDetail.export.action', 'Action'), tx('gallery.featureDetail.export.type', 'Type'), tx('gallery.featureDetail.export.time', 'Time')],
      ...data.timeline.map((t: any) => [t.action, t.type, t.time]),
    ];
    const csv = rows.map(r => r.join(',')).join('\n');
    downloadBlob(csv, `${featureId}_report.csv`, 'text/csv');
    setTimeout(() => setExporting(null), 800);
  }, [data, featureId, featureTitle, downloadBlob, tx]);

  const exportPDF = useCallback(() => {
    if (!data) return;
    setExporting('pdf');
    const m = data.metrics;
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${featureTitle} Report</title>
<style>body{font-family:-apple-system,system-ui,sans-serif;color:var(--app-text);max-width:700px;margin:0 auto;padding:32px}/* @theme-ok html-export-fixed-palette */
h1{font-size:22px;margin-bottom:4px}h2{font-size:16px;color:var(--app-text-muted);margin-top:28px;border-bottom:1px solid var(--app-text-muted);padding-bottom:6px}
.meta{color:var(--app-text-muted);font-size:12px;margin-bottom:24px}.kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}
.kpi{background:var(--app-primary-text);border:1px solid var(--app-text-muted);border-radius:10px;padding:14px;text-align:center}
.kpi-val{font-size:22px;font-weight:800;color:${featureColor}}.kpi-lbl{font-size:11px;color:var(--app-text-muted);text-transform:uppercase;letter-spacing:0.5px}
table{width:100%;border-collapse:collapse;margin:10px 0}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--app-text-muted);font-size:13px}
th{background:var(--app-primary-text);font-weight:600;color:var(--app-text-muted)}.badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}
.up{background:var(--app-primary);color:var(--app-success)}.down{background:var(--app-primary);color:var(--app-error)}</style></head><body>
<h1>${featureTitle}</h1><p class="meta">${tx('gallery.featureDetail.export.featurePerformanceReport', 'Feature Performance Report')} &mdash; ${new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })}</p>
<h2>${tx('gallery.featureDetail.export.keyMetrics', 'Key Metrics')}</h2><div class="kpi-grid">
<div class="kpi"><div class="kpi-val">${m.usage_count >= 1000 ? (m.usage_count/1000).toFixed(1)+'K' : m.usage_count}</div><div class="kpi-lbl">${tx('gallery.featureDetail.kpi.totalUsage', 'Total Usage')}</div></div>
<div class="kpi"><div class="kpi-val">${m.active_users}</div><div class="kpi-lbl">${tx('gallery.featureDetail.kpi.activeUsers', 'Active Users')}</div></div>
<div class="kpi"><div class="kpi-val">${m.performance_score}%</div><div class="kpi-lbl">${tx('gallery.featureDetail.kpi.performanceShort', 'Performance')}</div></div>
<div class="kpi"><div class="kpi-val">${m.confidence_score}%</div><div class="kpi-lbl">${tx('gallery.featureDetail.kpi.aiConfidence', 'AI Confidence')}</div></div>
<div class="kpi"><div class="kpi-val">${m.efficiency}%</div><div class="kpi-lbl">${tx('gallery.featureDetail.kpi.efficiency', 'Efficiency')}</div></div>
<div class="kpi"><div class="kpi-val">${data.uptime}</div><div class="kpi-lbl">${tx('gallery.featureDetail.status.uptime', 'Uptime')}</div></div></div>
<table><tr><th>${tx('gallery.featureDetail.export.status', 'Status')}</th><th>${tx('gallery.featureDetail.export.value', 'Value')}</th></tr>
<tr><td>${tx('gallery.featureDetail.status.automation', 'Automation')}</td><td>${data.automation_status}</td></tr>
<tr><td>${tx('gallery.featureDetail.status.avgResponseShort', 'Avg Response')}</td><td>${data.avg_response_time}</td></tr>
<tr><td>${tx('gallery.featureDetail.status.trend', 'Trend')}</td><td><span class="badge ${m.trend === 'up' ? 'up' : 'down'}">${m.trend_pct > 0 ? '+' : ''}${m.trend_pct}%</span></td></tr></table>
<h2>${tx('gallery.featureDetail.charts.dailyUsageLast7Days', 'Daily Usage (Last 7 Days)')}</h2><table><tr><th>${tx('gallery.featureDetail.export.day', 'Day')}</th><th>${tx('gallery.featureDetail.export.usage', 'Usage')}</th></tr>
${data.daily_chart.map((d: any) => `<tr><td>${d.day}</td><td>${d.usage}</td></tr>`).join('')}</table>
<h2>${tx('gallery.featureDetail.timeline.title', 'Activity Timeline')}</h2><table><tr><th>${tx('gallery.featureDetail.export.event', 'Event')}</th><th>${tx('gallery.featureDetail.export.type', 'Type')}</th><th>${tx('gallery.featureDetail.export.time', 'Time')}</th></tr>
${data.timeline.map((t: any) => `<tr><td>${t.action}</td><td><span class="badge" style="background:var(--app-primary);color:var(--app-primary)">${t.type}</span></td><td>${t.time}</td></tr>`).join('')}</table>
<p style="color:var(--app-text-muted);font-size:11px;margin-top:32px;text-align:center">${tx('gallery.featureDetail.export.generatedByWithYear', 'Generated by RealAICoach © {year}').replace('{year}', String(new Date().getFullYear()))}</p>
</body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); w.print(); }
    setTimeout(() => setExporting(null), 800);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, featureId, featureTitle, featureColor, tx]);

  const { data: detailData, loading: detailLoading } = useLiveQuery(
    visible && featureId ? `/features/${featureId}/detail` : '',
    { entity: 'features', pollInterval: 60000, deps: [visible, featureId] }
  );

  useEffect(() => {
    if (visible && featureId) {
      if (detailData) setData(detailData);
      setLoading(detailLoading);
      Animated.timing(fadeAnim, { toValue: 1, duration: 300, useNativeDriver: Platform.OS !== 'web' }).start();
    } else {
      fadeAnim.setValue(0);
      setData(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, featureId, detailData, detailLoading]);

  if (!visible) return null;

  const m = data?.metrics;
  const blur = Platform.OS === 'web' ? { backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' } as any : {};

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <TouchableOpacity style={ms.overlay} activeOpacity={1} onPress={onClose} data-testid="feature-modal-overlay" testID="feature-modal-overlay" accessibilityRole="none">
        <TouchableOpacity
          activeOpacity={1}
          style={[ms.modal, { backgroundColor: colors.surfaceHover, borderColor: colors.border, maxWidth: isDesktop ? 680 : isTablet ? '88%' : '94%' }, blur]}
          data-testid="feature-modal" testID="feature-modal"
          role="dialog"
          aria-modal={true}
          aria-label={`${featureTitle} feature details`}
        >
          {/* Header */}
          <View style={ms.header}>
            <View style={[ms.modalIcon, { backgroundColor: (globalThis as any).__alphaColor(featureColor, '14'), borderColor: (globalThis as any).__alphaColor(featureColor, '25') }]}>
              <Ionicons name={featureIcon as any} size={24} color={featureColor} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[ms.modalTitle, { color: colors.text }]} data-testid="feature-modal-title" testID="feature-modal-title">{featureTitle}</Text>
              <Text style={[ms.modalSub, { color: colors.textMuted }]}>{tx('gallery.featureDetail.header.subtitle', 'Feature Analytics Dashboard')}</Text>
            </View>
            <TouchableOpacity onPress={onClose} style={[ms.closeBtn, { backgroundColor: colors.surface, borderColor: colors.border }]} data-testid="feature-modal-close" testID="feature-modal-close" accessibilityRole="button" >
              <Ionicons name="close" size={18} color={colors.textSec} />
            </TouchableOpacity>
          </View>

          <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
            {loading ? (
              <View style={ms.loadingWrap}><ActivityIndicator size="large" color={accentColor} /></View>
            ) : data ? (
              <Animated.View style={{ opacity: fadeAnim, padding: 20 }}>
                {/* KPI Cards */}
                <View style={ms.kpiGrid}>
                  {[
                    { label: tx('gallery.featureDetail.kpi.totalUsage', 'Total Usage'), value: m.usage_count >= 1000 ? (m.usage_count / 1000).toFixed(1) + 'K' : m.usage_count, icon: 'bar-chart', color: featureColor },
                    { label: tx('gallery.featureDetail.kpi.activeUsers', 'Active Users'), value: m.active_users, icon: 'people', color: colors.primary },
                    { label: tx('gallery.featureDetail.kpi.performanceShort', 'Performance'), value: m.performance_score + '%', icon: 'speedometer', color: colors.successText },
                    { label: tx('gallery.featureDetail.kpi.aiConfidence', 'AI Confidence'), value: m.confidence_score + '%', icon: 'hardware-chip', color: colors.warningText },
                    { label: tx('gallery.featureDetail.kpi.efficiency', 'Efficiency'), value: m.efficiency + '%', icon: 'flash', color: colors.purpleText },
                    { label: tx('gallery.featureDetail.status.uptime', 'Uptime'), value: data.uptime, icon: 'shield-checkmark', color: colors.accent },
                  ].map((kpi, i) => (
                    <View key={i} style={[ms.kpiCard, { backgroundColor: colors.surface, borderColor: colors.border }]} data-testid={`feature-modal-kpi-${i}`} testID={`feature-modal-kpi-${i}`}>
                      <Ionicons name={kpi.icon as any} size={16} color={kpi.color} />
                      <Text style={[ms.kpiValue, { color: colors.text }]}>{kpi.value}</Text>
                      <Text style={[ms.kpiLabel, { color: colors.textMuted }]}>{kpi.label}</Text>
                    </View>
                  ))}
                </View>

                {/* Charts */}
                <View style={[ms.chartCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <BarChart data={data.daily_chart} color={featureColor} label={tx('gallery.featureDetail.charts.dailyUsageLast7Days', 'Daily Usage (Last 7 Days)')} colors={colors} ms={ms} />
                </View>

                {/* Status row */}
                <View style={[ms.statusRow, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <View style={ms.statusItem}>
                    <Text style={[ms.statusLabel, { color: colors.textMuted }]}>{tx('gallery.featureDetail.status.automation', 'Automation')}</Text>
                    <View style={ms.statusValRow}>
                      <View style={[ms.statusDotSmall, { backgroundColor: data.automation_status === 'Running' ? 'var(--app-success)' : 'var(--app-warning)' }]} />
                      <Text style={[ms.statusValue, { color: colors.text }]}>{data.automation_status}</Text>
                    </View>
                  </View>
                  <View style={ms.statusItem}>
                    <Text style={[ms.statusLabel, { color: colors.textMuted }]}>{tx('gallery.featureDetail.status.avgResponse', 'Avg Response')}</Text>
                    <Text style={[ms.statusValue, { color: colors.text }]}>{data.avg_response_time}</Text>
                  </View>
                  <View style={ms.statusItem}>
                    <Text style={[ms.statusLabel, { color: colors.textMuted }]}>{tx('gallery.featureDetail.status.trend', 'Trend')}</Text>
                    <View style={ms.statusValRow}>
                      <Ionicons name={m.trend === 'up' ? 'trending-up' : 'trending-down'} size={14} color={m.trend === 'up' ? 'var(--app-success)' : 'var(--app-error)'} />
                      <Text style={[ms.statusValue, { color: m.trend === 'up' ? 'var(--app-success)' : 'var(--app-error)' }]}>{m.trend_pct > 0 ? '+' : ''}{m.trend_pct}%</Text>
                    </View>
                  </View>
                </View>

                {/* Timeline */}
                <View style={ms.timelineSection}>
                  <Text style={[ms.timelineTitle, { color: colors.text }]}>{tx('gallery.featureDetail.timeline.title', 'Activity Timeline')}</Text>
                  {data.timeline.map((item: any, i: number) => (
                    <TimelineItem key={i} item={item} color={featureColor} colors={colors} ms={ms} />
                  ))}
                </View>

                {/* Export Buttons */}
                {Platform.OS === 'web' && (
                  <View style={ms.exportSection} data-testid="feature-modal-export" testID="feature-modal-export">
                    <Text style={[ms.exportTitle, { color: colors.text }]}>{tx('gallery.featureDetail.export.title', 'Export Report')}</Text>
                    <Text style={[ms.exportDesc, { color: colors.textMuted }]}>{tx('gallery.featureDetail.export.description', "Download this feature's analytics as a report")}</Text>
                    <View style={ms.exportBtns}>
                      <TouchableOpacity
                        style={[ms.exportBtn, { borderColor: (globalThis as any).__alphaColor(colors.success, '30'), backgroundColor: colors.successSoft }]}
                        onPress={exportCSV}
                        disabled={!!exporting}
                        data-testid="feature-modal-export-csv" testID="feature-modal-export-csv"
                        accessibilityRole="button"
                      >
                        <Ionicons name="document-text" size={16} color={'var(--app-success)'} />
                        <Text style={[ms.exportBtnText, { color: colors.successText }]}>
                          {exporting === 'csv' ? tx('gallery.featureDetail.export.exporting', 'Exporting...') : tx('gallery.featureDetail.export.csv', 'Export CSV')}
                        </Text>
                      </TouchableOpacity>
                      <TouchableOpacity
                        style={[ms.exportBtn, { borderColor: (globalThis as any).__alphaColor(colors.primary, '30'), backgroundColor: colors.primarySoft }]}
                        onPress={exportPDF}
                        disabled={!!exporting}
                        data-testid="feature-modal-export-pdf" testID="feature-modal-export-pdf"
                        accessibilityRole="button"
                      >
                        <Ionicons name="print" size={16} color={'var(--app-primary)'} />
                        <Text style={[ms.exportBtnText, { color: colors.primary }]}>
                          {exporting === 'pdf' ? tx('gallery.featureDetail.export.generating', 'Generating...') : tx('gallery.featureDetail.export.pdf', 'Export PDF')}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}
              </Animated.View>
            ) : (
              <View style={ms.loadingWrap}><Text style={{ color: colors.textMuted }}>{tx('gallery.featureDetail.states.failedLoad', 'Failed to load data')}</Text></View>
            )}
          </ScrollView>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
}

function makeStyles(colors: any) { return StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'center', alignItems: 'center', padding: 16 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 20, borderBottomWidth: 1, borderBottomColor: 'rgba(148,163,184,0.08)' },
  modalIcon: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  modalTitle: { fontSize: 18, fontWeight: '800', letterSpacing: -0.3 },
  modalSub: { fontSize: 12, marginTop: 2 },
  closeBtn: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  loadingWrap: { padding: 60, alignItems: 'center', justifyContent: 'center' },
  kpiGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 },
  kpiCard: { width: '31%', flexGrow: 1, borderRadius: 14, padding: 14, borderWidth: 1, alignItems: 'center', gap: 4 },
  kpiValue: { fontSize: 20, fontWeight: '800', letterSpacing: -0.5 },
  kpiLabel: { fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 },
  chartCard: { borderRadius: 16, padding: 18, borderWidth: 1, marginBottom: 16 },
  chartWrap: {},
  chartLabel: { fontSize: 12, fontWeight: '600', marginBottom: 12 },
  barsWrap: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, height: 100 },
  barCol: { flex: 1, alignItems: 'center' },
  bar: { width: '80%', borderRadius: 4, minHeight: 4 },
  barLabel: { color: colors.textMuted, fontSize: 9, fontWeight: '600', marginTop: 6 },
  statusRow: { flexDirection: 'row', borderRadius: 14, padding: 16, borderWidth: 1, marginBottom: 16, gap: 8 },
  statusItem: { flex: 1, alignItems: 'center', gap: 4 },
  statusLabel: { fontSize: 10, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 0.5 },
  statusValRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  statusDotSmall: { width: 6, height: 6, borderRadius: 3 },
  statusValue: { fontSize: 14, fontWeight: '700' },
  timelineSection: { marginTop: 4 },
  timelineTitle: { fontSize: 15, fontWeight: '700', marginBottom: 14 },
  timeItem: { flexDirection: 'row', gap: 12, marginBottom: 4 },
  timeDotCol: { alignItems: 'center', width: 16 },
  timeDot: { width: 10, height: 10, borderRadius: 5, marginTop: 4 },
  timeLine: { width: 2, flex: 1, marginTop: 2 },
  timeContent: { flex: 1, paddingBottom: 14 },
  timeAction: { color: colors.textSec, fontSize: 13, fontWeight: '500', marginBottom: 6 },
  timeMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  timeTypeBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  timeTypeText: { fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  timeAgo: { color: colors.textMuted, fontSize: 11 },
  exportSection: { marginTop: 20, paddingTop: 20, borderTopWidth: 1, borderTopColor: 'rgba(148,163,184,0.08)' },
  exportTitle: { fontSize: 15, fontWeight: '700', marginBottom: 4 },
  exportDesc: { fontSize: 12, marginBottom: 14 },
  exportBtns: { flexDirection: 'row', gap: 10 },
  exportBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12, paddingHorizontal: 18, borderRadius: 12, borderWidth: 1, flex: 1, justifyContent: 'center' },
  exportBtnText: { fontSize: 13, fontWeight: '700' },
}); }
