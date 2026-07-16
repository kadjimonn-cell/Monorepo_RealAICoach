import React from 'react';
import { View, Text, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import DataFreshnessIndicator from '../DataFreshnessIndicator';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import AutoFixBanner from './AutoFixBanner';

import { useAdminTheme } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
const _AC = {
  bg: 'var(--app-bg)', bgAlt: 'var(--app-bg)', card: 'var(--app-card-bg)', surface: 'var(--app-card-bg)', surfaceHover: 'var(--app-surface-hover)', border: 'var(--app-border)', borderStrong: 'var(--app-border-strong)',
  text: 'var(--app-text)', textSec: 'var(--app-text-sec)', textMuted: 'var(--app-text-muted)', textDim: 'var(--app-text-muted)',
  primary: 'var(--app-primary)', success: 'var(--app-success)' as any, warning: 'var(--app-warning)' as any, error: 'var(--app-error)' as any,
};
interface Props { colors: any; }

function makeT(AC: any) { return {
  bg: 'var(--app-bg)', card: AC.surface, border: 'var(--app-border)',
  text: AC.text, textSec: AC.textMuted, textMuted: AC.textDim,
  highlight: 'var(--app-error)',
}; }

const tx = (_key: string, fallback: string) => fallback;

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'var(--app-error)', high: 'var(--app-warning)', medium: 'var(--app-primary)', low: 'var(--app-success)', // @theme-ok brand/role/state identifier
};

const CATEGORY_ICONS: Record<string, string> = {
  Authentication: 'key', 'Threat Detection': 'shield', 'Incident Response': 'alert-circle',
  'Alert Management': 'notifications', 'Network Security': 'globe', Monitoring: 'analytics',
};

export default function SecurityRecommendationsPanel({ colors }: Props) {
  const { t } = useTranslation();
  const tx = (key: string, fallback: string) => {
    const value = t(key);
    return value === key ? fallback : value;
  };

  const AC = useAdminTheme();
  const T = React.useMemo(() => makeT(AC), [AC]);
  const { data, loading, refetch: loadRecommendations, lastUpdated } = useLiveQuery('/admin/security-recommendations/analyze?days=7', { entity: 'security', pollInterval: 60000 });

  if (loading) return <View style={{ padding: 40, alignItems: 'center' }}><ActivityIndicator size="large" color={T.highlight} /></View>;
  if (!data) return <View style={{ padding: 40, alignItems: 'center' }}><Text style={{ color: T.textMuted }}>{tx('admin.securityRecommendationsPanel.auto.text.001', 'Failed to load recommendations')}</Text></View>;

  const gradeColor = data.grade === 'A' ? 'var(--app-success)' : data.grade === 'B' ? 'var(--app-primary)' : data.grade === 'C' ? 'var(--app-warning)' : data.grade === 'D' ? 'var(--app-error)' : 'var(--app-error)';

  return (
    <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
      <AutoFixBanner domain="security_recs" />
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <View>
          <Text style={{ fontSize: 20, fontWeight: '800', color: T.text }} data-testid="sec-rec-title" testID="sec-rec-title">{tx('admin.securityRecommendationsPanel.auto.text.002', 'AI Security Analysis')}</Text>
          <Text style={{ fontSize: 12, color: T.textSec, marginTop: 2 }}>{tx('admin.securityRecommendationsPanel.auto.text.003', 'Proactive security recommendations powered by AI')}</Text>
        </View>
        <DataFreshnessIndicator lastUpdated={lastUpdated} onRefresh={loadRecommendations} isRefreshing={loading} accentColor={T.highlight} textColor={T.textMuted} />
      </View>

      {/* Risk Score Card */}
      <View style={{ flexDirection: 'row', gap: 14, marginBottom: 20 }} data-testid="sec-rec-score" testID="sec-rec-score">
        <View style={{ flex: 1, backgroundColor: T.card, borderRadius: 16, padding: 20, borderWidth: 1, borderColor: T.border, alignItems: 'center' }}>
          <View style={{ width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: gradeColor, alignItems: 'center', justifyContent: 'center', marginBottom: 8 }}>
            <Text style={{ fontSize: 28, fontWeight: '900', color: gradeColor }}>{data.grade}</Text>
          </View>
          <Text style={{ fontSize: 26, fontWeight: '800', color: T.text }}>{data.risk_score}/100</Text>
          <Text style={{ fontSize: 11, color: T.textMuted, fontWeight: '600', marginTop: 4 }}>{tx('admin.securityRecommendationsPanel.auto.text.004', 'Security Score')}</Text>
        </View>
        <View style={{ flex: 2 }}>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
            {[
              { label: 'Events', value: data.context_summary?.total_events, color: colors.primary },
              { label: 'Critical', value: data.context_summary?.critical_events, color: colors.error },
              { label: 'MFA %', value: `${data.context_summary?.mfa_adoption}%`, color: colors.accent },
              { label: 'Alerts', value: data.context_summary?.active_alerts, color: colors.warningText },
            ].map(s => (
              <View key={s.label} style={{ flex: 1, minWidth: 100, backgroundColor: T.card, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border }}>
                <Text style={{ fontSize: 20, fontWeight: '800', color: s.color }}>{typeof s.value === 'number' ? s.value.toLocaleString() : s.value}</Text>
                <Text style={{ fontSize: 10, color: T.textMuted, fontWeight: '600', marginTop: 2 }}>{s.label}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* Recommendations */}
      <Text style={{ fontSize: 16, fontWeight: '700', color: T.text, marginBottom: 12 }}>Recommendations ({data.recommendations?.length || 0})</Text>
      {(data.recommendations || []).map((rec: any, i: number) => (
        <View key={i} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: (globalThis as any).__alphaColor((SEVERITY_COLORS[rec.severity] || T.border), '30'), marginBottom: 10 }}
          data-testid={`sec-rec-item-${i}`} testID={`sec-rec-item-${i}`}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: (globalThis as any).__alphaColor((SEVERITY_COLORS[rec.severity] || AC.textDim), '15'), alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={(CATEGORY_ICONS[rec.category] || 'shield') as any} size={16} color={SEVERITY_COLORS[rec.severity] || AC.textDim} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 14, fontWeight: '700', color: T.text }}>{rec.title}</Text>
              <View style={{ flexDirection: 'row', gap: 6, marginTop: 3 }}>
                <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((SEVERITY_COLORS[rec.severity] || AC.textDim), '20') }}>
                  <Text style={{ fontSize: 9, fontWeight: '700', color: SEVERITY_COLORS[rec.severity] || AC.textDim }}>{rec.severity?.toUpperCase()}</Text>
                </View>
                <Text style={{ fontSize: 10, color: T.textMuted }}>{rec.category}</Text>
              </View>
            </View>
          </View>
          <Text style={{ fontSize: 12, color: T.textSec, lineHeight: 18, marginBottom: 8 }}>{rec.description}</Text>
          <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 6, backgroundColor: T.bg, borderRadius: 8, padding: 10 }}>
            <Ionicons name="bulb" size={14} color={'var(--app-warning)'} style={{ marginTop: 1 }} />
            <Text style={{ fontSize: 11, color: T.text, flex: 1, lineHeight: 16 }}>{rec.action}</Text>
          </View>
        </View>
      ))}

      {/* AI Insights */}
      {data.ai_insights && data.ai_insights.length > 0 && (
        <View style={{ marginTop: 10 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Ionicons name="sparkles" size={16} color={'var(--app-primary)'} />
            <Text style={{ fontSize: 16, fontWeight: '700', color: T.text }}>{tx('admin.securityRecommendationsPanel.auto.text.005', 'AI Insights')}</Text>
          </View>
          {data.ai_insights.map((insight: any, i: number) => (
            <View key={i} style={{ backgroundColor: T.card, borderRadius: 14, padding: 16, borderWidth: 1, borderColor: colors.accentSoft, marginBottom: 8 }}
              data-testid={`sec-ai-insight-${i}`} testID={`sec-ai-insight-${i}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                <View style={{ paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4, backgroundColor: (globalThis as any).__alphaColor((SEVERITY_COLORS[insight.priority] || 'var(--app-primary)'), '20') }}>
                  <Text style={{ fontSize: 9, fontWeight: '700', color: SEVERITY_COLORS[insight.priority] || 'var(--app-primary)' }}>{insight.priority?.toUpperCase()}</Text>
                </View>
              </View>
              <Text style={{ fontSize: 12, color: T.textSec, lineHeight: 18, marginBottom: 6 }}>{insight.insight}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 6, backgroundColor: T.bg, borderRadius: 8, padding: 10 }}>
                <Ionicons name="arrow-forward" size={12} color={T.highlight} style={{ marginTop: 1 }} />
                <Text style={{ fontSize: 11, color: T.text, flex: 1 }}>{insight.action}</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      <Text style={{ fontSize: 10, color: T.textMuted, textAlign: 'center', marginTop: 16, marginBottom: 20 }}>
        Analysis performed at {data.analyzed_at?.slice(0, 19).replace('T', ' ')} UTC
      </Text>
    </ScrollView>
  );
}
