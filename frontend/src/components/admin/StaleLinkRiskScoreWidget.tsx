import React from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useLiveQuery } from '../../hooks/useLiveQuery';
import { useTheme } from '../../context/ThemeContext';
import { getAdminColors } from '../../hooks/useAdminTheme';
import { useTranslation } from '../../hooks/useTranslation';
import { MiniSparkline } from './MiniSparkline';

const tx = (_key: string, fallback: string) => fallback;

export const StaleLinkRiskScoreWidget = () => {
  const router = useRouter();
  const { darkMode, colors } = useTheme();
  const C = getAdminColors(darkMode);
  const toneMap = {
    low: { color: colors.successText, bg: `${colors.successText}18`, icon: 'checkmark-circle' },
    medium: { color: colors.warning, bg: `${colors.warning}18`, icon: 'alert-circle' },
    high: { color: colors.warningText, bg: `${colors.warningText}18`, icon: 'warning' },
    critical: { color: colors.error, bg: `${colors.error}18`, icon: 'warning' },
  };
  const { data, loading, refetch } = useLiveQuery('/admin/platform-health/executive/stale-link-risk', {
    entity: 'stale-link-risk',
    pollInterval: 60000,
  });

  if (loading && !data) {
    return (
      <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, alignItems: 'center' }} data-testid="stale-link-risk-loading" testID="stale-link-risk-loading">
        <ActivityIndicator color={C.primary} />
        <Text style={{ color: C.textMuted, fontSize: 12, marginTop: 10 }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.001', 'Loading stale-link risk…')}</Text>
      </View>
    );
  }

  const band = String(data?.band || 'medium').toLowerCase() as keyof typeof toneMap;
  const tone = toneMap[band] || toneMap.medium;
  const metrics = data?.metrics || {};
  const files = Array.isArray(data?.sample_files) ? data.sample_files : [];
  const drivers = Array.isArray(data?.drivers) ? data.drivers : [];
  const trend = Array.isArray(data?.trend_7d) ? data.trend_7d : [];
  const trendScores = trend.map((row: any) => Number(row?.score || 0));
  const trendDelta = Number(metrics?.risk_score_delta_7d ?? 0);
  const trendDirection = trendDelta > 0 ? 'Improving' : trendDelta < 0 ? 'Worsening' : 'Stable';

  return (
    <View style={{ backgroundColor: C.card, borderRadius: 14, padding: 20, borderWidth: 1, borderColor: C.border, marginBottom: 20 }} data-testid="stale-link-risk-widget" testID="stale-link-risk-widget">
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 220 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: tone.bg, alignItems: 'center', justifyContent: 'center' }} data-testid="stale-link-risk-icon" testID="stale-link-risk-icon">
              <Ionicons name={tone.icon as any} size={20} color={tone.color} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ color: C.text, fontSize: 15, fontWeight: '800' }} data-testid="stale-link-risk-title" testID="stale-link-risk-title">{tx('admin.staleLinkRiskScoreWidget.auto.text.002', 'Stale Link Risk Score')}</Text>
              <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 3 }} data-testid="stale-link-risk-subtitle" testID="stale-link-risk-subtitle">{tx('admin.staleLinkRiskScoreWidget.auto.text.003', 'Admin Console early warning for stale route references and broken-link drift.')}</Text>
            </View>
          </View>
          <Text style={{ color: tone.color, fontSize: 38, fontWeight: '900', marginTop: 18 }} data-testid="stale-link-risk-score" testID="stale-link-risk-score">{String(data?.score ?? '--')}</Text>
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '700', textTransform: 'uppercase' }} data-testid="stale-link-risk-band" testID="stale-link-risk-band">{band} risk</Text>
          <Text style={{ color: C.textSec, fontSize: 12, lineHeight: 18, marginTop: 8 }} data-testid="stale-link-risk-summary" testID="stale-link-risk-summary">{data?.summary || 'No summary available.'}</Text>
        </View>

        <View style={{ gap: 8, alignItems: 'flex-end' }}>
          <TouchableOpacity onPress={() => router.push('/admin-console?category=operations&tab=platform-health' as any)} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: `${C.primary}16`, borderWidth: 1, borderColor: `${C.primary}30` }} data-testid="stale-link-risk-open-platform-health" testID="stale-link-risk-open-platform-health">
            <Text style={{ color: C.primary, fontSize: 12, fontWeight: '800' }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.004', 'Open Platform Health')}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => refetch()} style={{ paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: C.bgSoft, borderWidth: 1, borderColor: C.border }} data-testid="stale-link-risk-refresh" testID="stale-link-risk-refresh">
            <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.005', 'Refresh')}</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 16 }}>
        {[
          { id: 'latest', label: 'Latest stale URLs', value: metrics.latest_stale_urls ?? 0 },
          { id: 'avg', label: '7d average', value: metrics.avg_stale_urls_7d ?? 0 },
          { id: 'route', label: 'Route health', value: `${metrics.route_health_score_7d ?? 100}/100` },
          { id: 'mttr', label: 'MTTR 7d', value: `${metrics.mttr_minutes_7d ?? 0}m` },
        ].map((item) => (
          <View key={item.id} style={{ flex: 1, minWidth: 140, backgroundColor: C.bg, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: C.border }} data-testid={`stale-link-risk-metric-${item.id}`} testID={`stale-link-risk-metric-${item.id}`}>
            <Text style={{ color: C.textMuted, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{item.label}</Text>
            <Text style={{ color: C.text, fontSize: 22, fontWeight: '900', marginTop: 6 }}>{String(item.value)}</Text>
          </View>
        ))}
      </View>

      <View style={{ marginTop: 14, backgroundColor: C.bg, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid="stale-link-risk-trend-card" testID="stale-link-risk-trend-card">
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }} data-testid="stale-link-risk-trend-title" testID="stale-link-risk-trend-title">{tx('admin.staleLinkRiskScoreWidget.auto.text.006', 'Risk Score Trend (7d)')}</Text>
          <Text style={{ color: trendDelta > 0 ? colors.successText : trendDelta < 0 ? colors.error : C.textMuted, fontSize: 11, fontWeight: '800' }} data-testid="stale-link-risk-trend-delta" testID="stale-link-risk-trend-delta">
            {trendDelta > 0 ? '+' : ''}{trendDelta.toFixed(1)} • {trendDirection}
          </Text>
        </View>
        <View style={{ marginTop: 10 }} data-testid="stale-link-risk-trend-sparkline-wrap" testID="stale-link-risk-trend-sparkline-wrap">
          <MiniSparkline data={trendScores} color={tone.color} width={200} height={46} testId="stale-link-risk-trend-sparkline" />
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 }}>
          <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="stale-link-risk-trend-start" testID="stale-link-risk-trend-start">{trend[0]?.date || '—'}</Text>
          <Text style={{ color: C.textMuted, fontSize: 10 }} data-testid="stale-link-risk-trend-end" testID="stale-link-risk-trend-end">{trend[trend.length - 1]?.date || '—'}</Text>
        </View>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 16 }}>
        <View style={{ flex: 1, minWidth: 260, backgroundColor: C.bg, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid="stale-link-risk-drivers" testID="stale-link-risk-drivers">
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.007', 'Top risk drivers')}</Text>
          {drivers.slice(0, 3).map((driver: string, index: number) => (
            <Text key={`${driver}-${index}`} style={{ color: C.textSec, fontSize: 11, lineHeight: 17, marginTop: 8 }} data-testid={`stale-link-risk-driver-${index}`} testID={`stale-link-risk-driver-${index}`}>• {driver}</Text>
          ))}
        </View>

        <View style={{ flex: 1, minWidth: 260, backgroundColor: C.bg, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: C.border }} data-testid="stale-link-risk-files" testID="stale-link-risk-files">
          <Text style={{ color: C.text, fontSize: 12, fontWeight: '800' }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.008', 'Latest affected files')}</Text>
          {files.length === 0 ? (
            <Text style={{ color: C.textMuted, fontSize: 11, marginTop: 8 }} data-testid="stale-link-risk-files-empty" testID="stale-link-risk-files-empty">{tx('admin.staleLinkRiskScoreWidget.auto.text.009', 'No stale references detected in the latest scan.')}</Text>
          ) : files.map((file: any, index: number) => (
            <View key={`${file.file}-${index}`} style={{ marginTop: 8, paddingTop: 8, borderTopWidth: index === 0 ? 0 : 1, borderTopColor: C.border }} data-testid={`stale-link-risk-file-${index}`} testID={`stale-link-risk-file-${index}`}>
              <Text style={{ color: C.text, fontSize: 11, fontWeight: '700' }}>{String(file.file).split('/').slice(-2).join('/')}</Text>
              <Text style={{ color: C.textMuted, fontSize: 10, marginTop: 3 }}>line {String(file.line ?? '—')} • {String(file.pattern || 'stale-reference')}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={{ marginTop: 14, padding: 12, borderRadius: 12, backgroundColor: tone.bg, borderWidth: 1, borderColor: `${tone.color}30` }} data-testid="stale-link-risk-recommendation" testID="stale-link-risk-recommendation">
        <Text style={{ color: tone.color, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' }}>{tx('admin.staleLinkRiskScoreWidget.auto.text.010', 'Recommended action')}</Text>
        <Text style={{ color: C.text, fontSize: 12, lineHeight: 18, marginTop: 4 }}>{data?.recommended_action || 'Review the latest Platform Health scan and clear stale references.'}</Text>
      </View>
    </View>
  );
};

export default StaleLinkRiskScoreWidget;
/* i18n-probe t('i18n.auto.probe') */
