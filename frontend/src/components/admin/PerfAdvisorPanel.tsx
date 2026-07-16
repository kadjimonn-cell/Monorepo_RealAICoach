import React, { useState, useCallback } from 'react';
import { View, Text, ScrollView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';
import AutoFixBanner from './AutoFixBanner';
import { useTheme } from '../../context/ThemeContext';
import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { useHybridPolling } from '../../hooks/useHybridPolling';

const BASE_T = {
  bg: 'var(--app-bg)', card: 'var(--app-card-bg)', border: 'var(--app-border)', text: 'var(--app-text)',
  textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', primary: 'var(--app-primary)', success: 'var(--app-success)',
  warning: 'var(--app-warning)', error: 'var(--app-error)', purple: 'var(--app-primary)', cyan: 'var(--app-primary)',
  successSoft: 'var(--app-primary)',
  successBorder: 'var(--app-primary)',
};

let T = { ...BASE_T };

const getPalette = (darkMode: boolean) => {
  const AC = getAdminColors(darkMode);
  return {
    ...BASE_T,
    bg: AC.bg,
    card: AC.card,
    border: AC.border,
    text: AC.text,
    textSec: AC.textSec,
    textMuted: AC.textMuted,
    primary: AC.primary,
    success: AC.success,
    warning: AC.warning,
    error: AC.error,
    purple: AC.purple,
    cyan: AC.info,
    successSoft: AC.successSoft,
    successBorder: AC.success,
  };
};

export default function PerfAdvisorPanel({ colors }: { colors: any }) {
  const ON_PRIMARY = 'rgb(255,255,255)';
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const { darkMode } = useTheme();
  T = getPalette(darkMode);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [metrics, setMetrics] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/perf-advisor/metrics');
      setMetrics(res.data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchMetrics(); }, [fetchMetrics]);

  useHybridPolling({
    enabled: true,
    errorScope: 'admin/perf-advisor/hybrid-refresh',
    onTick: fetchMetrics,
    runOnMount: false,
    slowIntervalMs: 45000,
    fastIntervalMs: 15000,
  });

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await api.get('/admin/perf-advisor/analyze');
      setAnalysis(res.data);
    } catch (e) { console.error(e); }
    finally { setAnalyzing(false); }
  };

  if (loading) return (
    <View style={{ padding: 40, alignItems: 'center' }} data-testid="perf-advisor-loading" testID="perf-advisor-loading">
      <AutoFixBanner domain="perf_advisor" />
      <ActivityIndicator size="large" color={T.cyan} />
      <Text style={{ color: T.textSec, marginTop: 12 }}>{tx('admin.perfAdvisorPanel.auto.text.001', 'Collecting metrics...')}</Text>
    </View>
  );

  return (
    <ScrollView style={{ flex: 1 }} data-testid="perf-advisor-panel" testID="perf-advisor-panel">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 40, height: 40, borderRadius: 10, backgroundColor: T.bg, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="speedometer" size={22} color={T.cyan} />
          </View>
          <View>
            <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{tx('admin.perfAdvisorPanel.auto.text.002', 'Performance Advisor')}</Text>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{tx('admin.perfAdvisorPanel.auto.text.003', 'AI-Powered Optimization (GPT-4o)')}</Text>
          </View>
        </View>
        <TouchableOpacity data-testid="perf-run-analysis-btn" testID="perf-run-analysis-btn" onPress={runAnalysis} disabled={analyzing}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: T.cyan, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, opacity: analyzing ? 0.6 : 1 }}>
          {analyzing ? <ActivityIndicator size="small" color={ON_PRIMARY} /> : <Ionicons name="flash" size={16} color={ON_PRIMARY} />}
          <Text style={{ color: ON_PRIMARY, fontSize: 12, fontWeight: '600' }}>{analyzing ? 'Analyzing...' : 'Run AI Analysis'}</Text>
        </TouchableOpacity>
      </View>

      {/* System Metrics */}
      {metrics && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
          <MetricCard label="CPU" value={`${metrics.system.cpu_percent}%`} icon="hardware-chip" color={metrics.system.cpu_percent > 70 ? T.error : T.success} />
          <MetricCard label="Memory" value={`${metrics.system.memory_used_percent}%`} icon="server" color={metrics.system.memory_used_percent > 80 ? T.error : T.success} />
          <MetricCard label="Disk Free" value={`${metrics.system.disk_free_gb}GB`} icon="disc" color={T.primary} />
          <MetricCard label="DB Size" value={`${metrics.database.data_size_mb}MB`} icon="layers" color={T.purpleText} />
        </View>
      )}

      {/* API Latencies */}
      {metrics?.api_latencies && (
        <View style={{ backgroundColor: T.card, borderRadius: 10, padding: 14, marginBottom: 16, borderWidth: 1, borderColor: T.border }}>
          <Text style={{ color: T.text, fontWeight: '600', fontSize: 13, marginBottom: 10 }}>{tx('admin.perfAdvisorPanel.auto.text.004', 'API Response Times')}</Text>
          {Object.entries(metrics.api_latencies).map(([ep, d]: [string, any]) => (
            <View key={ep} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
              <Text style={{ color: T.textSec, fontSize: 12 }}>{ep}</Text>
              <Text style={{ color: d.latency_ms < 100 ? T.success : d.latency_ms < 300 ? T.warning : T.error, fontSize: 12, fontWeight: '600' }}>
                {d.latency_ms}ms
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* AI Analysis Results */}
      {analysis && (
        <View data-testid="perf-analysis-result" testID="perf-analysis-result">
          <View style={{ backgroundColor: T.card, borderRadius: 12, padding: 16, marginBottom: 16, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
              <View>
                <Text style={{ color: T.textMuted, fontSize: 11 }}>{tx('admin.perfAdvisorPanel.auto.text.005', 'Performance Score')}</Text>
                <Text style={{ color: gradeColor(analysis.overall_score), fontSize: 36, fontWeight: '800' }}>{analysis.overall_score}/100</Text>
              </View>
              <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: (globalThis as any).__alphaColor(gradeColor(analysis.overall_score), '20'), alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: gradeColor(analysis.overall_score), fontSize: 20, fontWeight: '800' }}>{analysis.grade}</Text>
              </View>
            </View>
            <Text style={{ color: T.textSec, fontSize: 12 }}>{analysis.summary}</Text>
          </View>

          {analysis.recommendations?.length > 0 && (
            <View style={{ gap: 8, marginBottom: 16 }}>
              <Text style={{ color: T.text, fontWeight: '600', fontSize: 14 }}>{tx('admin.perfAdvisorPanel.auto.text.006', 'Recommendations')}</Text>
              {analysis.recommendations.map((r: any, i: number) => (
                <View key={i} style={{ backgroundColor: T.card, borderRadius: 8, padding: 12, borderWidth: 1, borderColor: T.border }}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor(priorityColor(r.priority), '20') }}>
                      <Text style={{ color: priorityColor(r.priority), fontSize: 10, fontWeight: '700' }}>{r.priority?.toUpperCase()}</Text>
                    </View>
                    <Text style={{ color: T.textMuted, fontSize: 10 }}>{r.category}</Text>
                    {r.estimated_impact && <Text style={{ color: T.successText, fontSize: 10, marginLeft: 'auto' }}>+{r.estimated_impact}%</Text>}
                  </View>
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{r.title}</Text>
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 2 }}>{r.description}</Text>
                </View>
              ))}
            </View>
          )}

          {analysis.quick_wins?.length > 0 && (
            <View style={{ backgroundColor: T.successSoft, borderRadius: 10, padding: 14, borderWidth: 1, borderColor: T.successBorder }}>
              <Text style={{ color: T.successText, fontWeight: '600', fontSize: 13, marginBottom: 8 }}>{tx('admin.perfAdvisorPanel.auto.text.007', 'Quick Wins')}</Text>
              {analysis.quick_wins.map((w: string, i: number) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 3 }}>
                  <Ionicons name="checkmark-circle" size={14} color={T.successText} />
                  <Text style={{ color: T.textSec, fontSize: 12 }}>{w}</Text>
                </View>
              ))}
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}

function MetricCard({ label, value, icon, color }: any) {
  return (
    <View style={{ flex: 1, minWidth: 130, backgroundColor: T.card, borderRadius: 10, padding: 12, borderWidth: 1, borderColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <Ionicons name={icon} size={14} color={color} />
        <Text style={{ color: T.textMuted, fontSize: 11 }}>{label}</Text>
      </View>
      <Text style={{ color: T.text, fontSize: 18, fontWeight: '700' }}>{value}</Text>
    </View>
  );
}

function gradeColor(score: number) { return score >= 80 ? T.success : score >= 60 ? T.warning : T.error; }
function priorityColor(p: string) { return p === 'critical' ? T.error : p === 'high' ? T.warning : p === 'medium' ? T.primary : T.textMuted; }
