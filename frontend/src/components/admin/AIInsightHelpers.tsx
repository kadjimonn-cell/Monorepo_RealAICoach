import React, { useState, useCallback, useEffect } from 'react';
import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { View, Text, ActivityIndicator, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

const tx = (_key: string, fallback: string) => fallback;

function makeT(AC: any) { return {
  bg: AC.bg,
  bgSoft: AC.bgSoft,
  card: AC.card,
  border: AC.border,
  text: AC.text,
  textSec: AC.textSec,
  textMuted: AC.textMuted,
  textDim: AC.textDim || AC.textMuted,
  primary: AC.primary,
  primaryText: AC.primaryText || AC.buttonText || AC.text,
  success: AC.success,
  successText: AC.successText || AC.success,
  successSoft: AC.successSoft || `${AC.success}20`,
  warning: AC.warning,
  warningText: AC.warningText || AC.warning,
  warningSoft: AC.warningSoft || `${AC.warning}20`,
  error: AC.error,
  errorText: AC.errorText || AC.error,
  errorSoft: AC.errorSoft || `${AC.error}20`,
  purple: AC.purple,
  purpleText: AC.purpleText || AC.purple,
  cyan: AC.cyan || AC.info,
  teal: AC.teal || AC.cyan || AC.info,
  ai: AC.cyan || AC.info,
  orange: AC.orange,
  orangeText: AC.orangeText || AC.orange,
  pink: AC.pink || AC.purple,
}; }

interface InsightConfig {
  cacheKey: string;
  postEndpoint: string;
  title: string;
  subtitle: string;
  scoreKey: string;
  scoreLabel: string;
  summaryKey: string;
  sections: {
    key: string;
    title: string;
    icon: string;
    renderItem: (item: any, idx: number, total: number) => React.ReactNode;
  }[];
}

export function useAiInsight(cacheKey: string, postEndpoint: string) {
  const AC = useAdminTheme();
  const _T = React.useMemo(() => makeT(AC), [AC]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const cached = await api.get(`/admin/ai-insights/latest/${cacheKey}`);
      if (cached.data && !cached.data.status) {
        setData(cached.data);
        setLoading(false);
        return;
      }
      const res = await api.post(`/admin/ai-insights/${postEndpoint}`);
      setData(res.data);
    } catch { setData(null); }
    setLoading(false);
  }, [cacheKey, postEndpoint]);

  return { data, loading, run };
}

export function AIInsightPanel({ config, data, loading, onRun }: {
  config: InsightConfig;
  data: any;
  loading: boolean;
  onRun: () => void;
}) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!data && !loading) onRun(); }, []);

  if (loading) return (
    <View style={{ paddingVertical: 40, alignItems: 'center' }}>
      <ActivityIndicator size="large" color={T.ai} />
      <Text style={{ color: T.textSec, marginTop: 8, fontSize: 12 }}>GPT-4o analyzing {config.subtitle}...</Text>
    </View>
  );

  if (!data || data.status === 'no_data') return (
    <View style={{ alignItems: 'center', paddingVertical: 32 }}>
      <Ionicons name="sparkles" size={36} color={T.ai} style={{ marginBottom: 12 }} />
      <Text style={{ color: T.textSec, fontSize: 13, marginBottom: 16 }}>{tx('admin.aIInsightHelpers.auto.text.001', 'AI analysis not yet generated')}</Text>
      <TouchableOpacity onPress={onRun} style={{ backgroundColor: T.ai, paddingHorizontal: 24, paddingVertical: 12, borderRadius: 12 }} data-testid={`${config.cacheKey}-ai-run-btn`} testID={`${config.cacheKey}-ai-run-btn`}>
        <Text style={{ color: T.primaryText, fontWeight: '700', fontSize: 14 }}>{tx('admin.aIInsightHelpers.auto.text.002', 'Run AI Analysis')}</Text>
      </TouchableOpacity>
    </View>
  );

  const score = data[config.scoreKey] ?? 0;
  const scoreColor = score >= 70 ? T.error : score >= 40 ? T.warning : T.success;
  const summary = data[config.summaryKey] || '';

  return (
    <View style={{ gap: 14 }} data-testid={`${config.cacheKey}-ai-insights`} testID={`${config.cacheKey}-ai-insights`}>
      {/* Header Card */}
      <View style={{ backgroundColor: T.card, borderRadius: 14, padding: 18, borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '30') }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(T.ai, '20'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name="sparkles" size={16} color={T.ai} />
            </View>
            <View>
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800' }}>{config.scoreLabel}</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>{tx('admin.aIInsightHelpers.auto.text.003', 'Powered by GPT-4o')}</Text>
            </View>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Text style={{ color: scoreColor, fontSize: 28, fontWeight: '900' }}>{score}</Text>
            <Text style={{ color: scoreColor, fontSize: 9, fontWeight: '700' }}>/100</Text>
          </View>
        </View>
        {summary ? <Text style={{ color: T.textSec, fontSize: 12, lineHeight: 18 }}>{summary}</Text> : null}
      </View>

      {/* Dynamic Sections */}
      {config.sections.map(section => {
        const items = data[section.key];
        if (!items?.length) return null;
        return (
          <View key={section.key} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: T.border }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Ionicons name={section.icon as any} size={14} color={T.ai} />
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700' }}>{section.title}</Text>
            </View>
            {items.map((item: any, idx: number) => section.renderItem(item, idx, items.length))}
          </View>
        );
      })}

      {/* Refresh button */}
      <TouchableOpacity onPress={onRun} style={{ backgroundColor: (globalThis as any).__alphaColor(T.ai, '15'), borderWidth: 1, borderColor: (globalThis as any).__alphaColor(T.ai, '40'), paddingVertical: 10, borderRadius: 10, alignItems: 'center' }} data-testid={`${config.cacheKey}-ai-refresh-btn`} testID={`${config.cacheKey}-ai-refresh-btn`}>
        <Text style={{ color: T.ai, fontSize: 12, fontWeight: '700' }}>{tx('admin.aIInsightHelpers.auto.text.004', 'Refresh AI Analysis')}</Text>
      </TouchableOpacity>
      {data.created_at && <Text style={{ color: T.textMuted, fontSize: 9, textAlign: 'center' }}>Last analyzed: {new Date(data.created_at).toLocaleString()}</Text>}
    </View>
  );
}

/* Reusable render helpers */
export function PriorityItem({ item, idx, total }: { item: any; idx: number; total: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  const pColor = (item.priority ?? 3) <= 2 ? T.error : (item.priority ?? 3) <= 3 ? T.warning : T.success;
  return (
    <View style={{ paddingVertical: 10, borderBottomWidth: idx < total - 1 ? 1 : 0, borderBottomColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor(pColor, '20'), alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ color: pColor, fontSize: 10, fontWeight: '800' }}>{item.priority ?? idx + 1}</Text>
        </View>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600', flex: 1 }}>{item.strategy || item.action || item.recommendation || item.improvement || item.tip || ''}</Text>
      </View>
      {item.description && <Text style={{ color: T.textSec, fontSize: 11, marginLeft: 28 }}>{item.description}</Text>}
      <View style={{ flexDirection: 'row', gap: 8, marginLeft: 28, marginTop: 4, flexWrap: 'wrap' }}>
        {item.expected_lift && <Badge label={item.expected_lift} color={T.successText} />}
        {item.expected_impact && <Badge label={item.expected_impact} color={T.successText} />}
        {item.effort && <Badge label={`Effort: ${item.effort}`} color={T.warningText} />}
        {item.impact && <Badge label={`Impact: ${item.impact}`} color={T.primary} />}
        {item.category && <Badge label={item.category} color={T.cyan} />}
        {item.timeline && <Badge label={item.timeline} color={T.purpleText} />}
      </View>
    </View>
  );
}

export function FindingItem({ item, idx, total }: { item: any; idx: number; total: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  const sColor = item.severity === 'critical' ? T.error : item.severity === 'high' ? 'var(--app-warning)' : item.severity === 'medium' ? T.warning : T.success;
  return (
    <View style={{ paddingVertical: 10, borderBottomWidth: idx < total - 1 ? 1 : 0, borderBottomColor: T.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <View style={{ backgroundColor: (globalThis as any).__alphaColor(sColor, '18'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
          <Text style={{ color: sColor, fontSize: 9, fontWeight: '700' }}>{(item.severity || 'info').toUpperCase()}</Text>
        </View>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600', flex: 1 }}>{item.finding || item.factor || item.anomaly || item.issue || ''}</Text>
      </View>
      {(item.recommendation || item.mitigation || item.evidence || item.description || item.significance) && (
        <Text style={{ color: T.textSec, fontSize: 11, marginLeft: 4, marginTop: 2 }}>{item.recommendation || item.mitigation || item.evidence || item.description || item.significance}</Text>
      )}
    </View>
  );
}

export function Badge({ label, color }: { label: string; color: string }) {
  return (
    <View style={{ backgroundColor: (globalThis as any).__alphaColor(color, '15'), paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
      <Text style={{ color, fontSize: 9, fontWeight: '700' }}>{label}</Text>
    </View>
  );
}

export function FunnelItem({ item, idx, total }: { item: any; idx: number; total: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ paddingVertical: 10, borderBottomWidth: idx < total - 1 ? 1 : 0, borderBottomColor: T.border }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{item.stage || item.step || ''}</Text>
        <Text style={{ color: T.error, fontSize: 11, fontWeight: '700' }}>{item.drop_off_pct || item.drop_off_rate || ''}</Text>
      </View>
      {item.issue && <Text style={{ color: T.textSec, fontSize: 11 }}>{item.issue}</Text>}
      {item.fix && <Text style={{ color: T.successText, fontSize: 11, marginTop: 2 }}>{item.fix}</Text>}
      {item.likely_cause && <Text style={{ color: T.textSec, fontSize: 11 }}>{item.likely_cause}</Text>}
    </View>
  );
}

export function QuickWinItem({ item, idx, total }: { item: any; idx: number; total: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  return (
    <View style={{ flexDirection: 'row', gap: 10, paddingVertical: 8, borderBottomWidth: idx < total - 1 ? 1 : 0, borderBottomColor: T.border }}>
      <View style={{ width: 24, height: 24, borderRadius: 12, backgroundColor: (globalThis as any).__alphaColor(T.success, '20'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name="flash" size={12} color={T.successText} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{item.action || item.booster || item.subject || item.topic || ''}</Text>
        <Text style={{ color: T.textSec, fontSize: 10, marginTop: 2 }}>{item.expected_impact || item.description || item.angle || item.predicted_open_rate || ''}</Text>
      </View>
    </View>
  );
}

export function TrendItem({ item, idx, total }: { item: any; idx: number; total: number }) {
  const __AC = useAdminTheme();
  const T = React.useMemo(() => makeT(__AC), [__AC]);
  const dirIcon = item.direction === 'up' ? 'trending-up' : item.direction === 'down' ? 'trending-down' : 'remove';
  const dirColor = item.concern_level === 'action' ? T.error : item.concern_level === 'watch' ? T.warning : T.success;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: idx < total - 1 ? 1 : 0, borderBottomColor: T.border }}>
      <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: (globalThis as any).__alphaColor(dirColor, '18'), alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={dirIcon as any} size={14} color={dirColor} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '600' }}>{item.metric || ''}</Text>
        <Text style={{ color: T.textSec, fontSize: 10 }}>{item.change || ''}</Text>
      </View>
      {item.concern_level && <Badge label={item.concern_level} color={dirColor} />}
    </View>
  );
}

/* i18n-probe t('i18n.auto.probe') */
